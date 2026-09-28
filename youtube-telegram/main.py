#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube para Telegram — App do Home Assistant.

Recebe links do YouTube, oferece opções de vídeo/áudio, baixa e entrega no chat.
Se o arquivo passa do limite do Telegram, sobe para o MinIO e envia um link
temporário (pré-assinado), apagando o objeto depois.
"""
from __future__ import annotations

import asyncio
import html
import logging
import logging.handlers
import secrets
import shutil
import sys
import tempfile
import time
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config as config_mod
import yt
from minio_store import MinioStore

LOG = logging.getLogger("youtube-telegram")

INTERVALO_PROGRESSO = 2.0
PREFIXO_MINIO = "youtube/"


# ---------------------------------------------------------------------------
# Helpers de mensagem
# ---------------------------------------------------------------------------

async def editar(mensagem, texto: str, **extra) -> None:
    """Edita a mensagem de status, ignorando erros de rede/rate limit."""
    try:
        await mensagem.edit_text(texto, parse_mode=ParseMode.HTML, **extra)
    except RetryAfter as e:
        await asyncio.sleep(float(e.retry_after))
    except Exception as e:  # noqa: BLE001
        LOG.debug("Falha ao editar a mensagem: %s", e)


async def tratar_erro(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Evita tracebacks feios para erros esperados do Telegram."""
    erro = context.error
    if isinstance(erro, BadRequest):
        LOG.warning("Requisição recusada pelo Telegram: %s", erro)
        return
    LOG.error("Erro não tratado ao processar update: %s", erro, exc_info=erro)


async def rodar_com_progresso(mensagem, estado: dict, titulo_html: str, rotulo: str,
                              funcao, intervalo: float, *args):
    """Roda uma função bloqueante informando o progresso na mesma mensagem."""
    parar = asyncio.Event()

    async def vigia():
        ultimo = None
        while not parar.is_set():
            texto = yt.texto_progresso_yt(estado, titulo_html, rotulo)
            if texto != ultimo:
                ultimo = texto
                await editar(mensagem, texto)
            try:
                await asyncio.wait_for(parar.wait(), intervalo)
            except asyncio.TimeoutError:
                pass

    tarefa = asyncio.create_task(vigia())
    try:
        return await asyncio.to_thread(funcao, estado, *args)
    finally:
        parar.set()
        await tarefa


def autorizado(update: Update, cfg: config_mod.Config) -> bool:
    usuario = update.effective_user
    if usuario is None:
        return False
    if not cfg.usuarios:
        return True  # config sem lista = liberado (útil para testar)
    return usuario.id in cfg.usuarios


# ---------------------------------------------------------------------------
# Entrega: chat do Telegram ou MinIO
# ---------------------------------------------------------------------------

async def enviar_telegram(mensagem, caminho: Path, selecao: dict, info: dict) -> None:
    titulo = info.get("title") or "vídeo"
    canal = info.get("uploader") or info.get("channel") or ""
    duracao = int(info.get("duration") or 0) or None
    tipo = selecao.get("tipo")
    altura = selecao.get("altura")
    rotulo = selecao.get("rotulo") or ""

    legenda = (f"🎵 <b>{html.escape(titulo)}</b>" if tipo == "audio"
               else f"🎬 <b>{html.escape(titulo)}</b>")
    if canal:
        legenda += f"\n👤 {html.escape(str(canal))}"
    if rotulo:
        legenda += f"\n{html.escape(rotulo)}"

    async def como_documento(erro: Exception) -> None:
        LOG.warning("Falha ao enviar como %s (%s); enviando como documento.", tipo or "mídia", erro)
        f.seek(0)
        await mensagem.reply_document(
            document=f, filename=caminho.name,
            caption=legenda, parse_mode=ParseMode.HTML,
        )

    with open(caminho, "rb") as f:
        if tipo == "audio":
            try:
                await mensagem.reply_audio(
                    audio=f, filename=caminho.name, title=titulo,
                    performer=str(canal) or None, duration=duracao,
                    caption=legenda, parse_mode=ParseMode.HTML,
                )
            except Exception as e:  # noqa: BLE001 — formato pode não ser aceito
                await como_documento(e)
            return

        extra = {"height": int(altura)} if altura else {}
        try:
            await mensagem.reply_video(
                video=f, filename=caminho.name, duration=duracao,
                supports_streaming=True, caption=legenda,
                parse_mode=ParseMode.HTML, **extra,
            )
        except Exception as e:  # noqa: BLE001 — formato pode não ser aceito
            await como_documento(e)


async def _apagar_em(store: MinioStore, objeto: str, minutos: float,
                     apagar: dict, token: str) -> None:
    await asyncio.sleep(max(1.0, float(minutos)) * 60)
    await asyncio.to_thread(store.apagar, objeto)
    apagar.pop(token, None)


async def entregar(mensagem, destino: Path, selecao: dict, info: dict,
                   cfg: config_mod.Config, store: MinioStore | None,
                   apagar: dict, usuario_id: int) -> None:
    tamanho = destino.stat().st_size
    titulo = info.get("title") or "vídeo"
    icone = "🎵" if selecao.get("tipo") == "audio" else "🎬"
    rotulo = selecao.get("rotulo") or ""

    # 1) cabe no Telegram -> manda no chat
    if tamanho <= cfg.max_envio_bytes:
        await editar(mensagem, f"📤 Enviando <b>{html.escape(titulo)}</b> "
                               f"({yt.fmt_bytes(tamanho)}) no chat…")
        await enviar_telegram(mensagem, destino, selecao, info)
        await editar(
            mensagem,
            f"✅ <b>{html.escape(titulo)}</b>\n{icone} {html.escape(rotulo)} · "
            f"{yt.fmt_bytes(tamanho)} enviado no chat.",
        )
        return

    # 2) grande -> MinIO
    if store is None:
        raise RuntimeError(
            f"o arquivo tem {yt.fmt_bytes(tamanho)} e passa do limite de "
            f"{cfg.max_envio_mb} MB do Telegram, e o MinIO não está ativo/configurado. "
            "Ative o MinIO nas opções do App."
        )

    objeto = f"{PREFIXO_MINIO}{time.strftime('%Y%m%d-%H%M%S')}-{yt.slug(destino.name)}"
    await editar(
        mensagem,
        f"📤 <b>{html.escape(titulo)}</b> ({yt.fmt_bytes(tamanho)}) passou do limite "
        f"de {cfg.max_envio_mb} MB; subindo para o MinIO…",
    )
    await asyncio.to_thread(store.enviar, destino, objeto)
    url = await asyncio.to_thread(store.url_temporaria, objeto)

    token = secrets.token_hex(4)
    apagar[token] = {"objeto": objeto, "user": usuario_id}
    teclado = InlineKeyboardMarkup([[
        InlineKeyboardButton("🗑 Já baixei — apagar agora", callback_data=f"del|{token}")
    ]])
    texto = (
        f"📦 <b>{html.escape(titulo)}</b>\n"
        f"{icone} {html.escape(rotulo)} · {yt.fmt_bytes(tamanho)}\n\n"
        f"⚠️ Passa do limite de {cfg.max_envio_mb} MB do Telegram, então subi para o MinIO.\n"
        f"🔗 <b>Link temporário</b> (expira em {cfg.minio_expira_min} min):\n"
        f"{html.escape(url)}\n\n"
        f"🗑 Apago do MinIO automaticamente em ~{cfg.minio_apagar_min} min, "
        f"ou clique no botão abaixo quando terminar o download."
    )
    await editar(mensagem, texto, reply_markup=teclado)
    asyncio.create_task(_apagar_em(store, objeto, cfg.minio_apagar_min, apagar, token))


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: config_mod.Config = context.bot_data["cfg"]
    if not autorizado(update, cfg):
        await update.effective_message.reply_text("🔒 Não autorizado.")
        return
    minio = "ativado" if cfg.minio_configurado() else "desativado"
    await update.effective_message.reply_text(
        "🎬 <b>YouTube para Telegram</b>\n\n"
        "Me mande um <b>link do YouTube</b> e eu ofereço opções de vídeo e áudio. "
        f"Até {cfg.max_envio_mb} MB eu envio direto no chat; acima disso subo para o "
        "MinIO e te passo um link temporário.\n\n"
        f"• Limite de envio direto: <b>{cfg.max_envio_mb} MB</b>\n"
        f"• MinIO: <b>{minio}</b>\n"
        f"• Qualidade máxima de vídeo: <b>{cfg.yt_altura_maxima}p</b>\n"
        f"• Limite de duração: <b>{cfg.yt_duracao_max_min} min</b>\n\n"
        "Comandos: /start · /help · /id",
        parse_mode=ParseMode.HTML,
    )


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    usuario = update.effective_user
    await update.effective_message.reply_text(
        f"Seu ID: <code>{usuario.id}</code>\n"
        f"Chat: <code>{update.effective_chat.id}</code>\n\n"
        "Use o ID na opção <code>usuarios_autorizados</code> do App.",
        parse_mode=ParseMode.HTML,
    )


async def tratar_links(update: Update, context: ContextTypes.DEFAULT_TYPE, urls: list[str]) -> None:
    cfg: config_mod.Config = context.bot_data["cfg"]
    msg = update.effective_message
    if not cfg.yt_ativo:
        await msg.reply_text("🔗 O download do YouTube está desativado nas opções do App.")
        return

    pendentes: dict = context.bot_data.setdefault("yt_pendentes", {})
    for url in urls[:3]:
        aviso = await msg.reply_text("🔎 Verificando o vídeo…")
        try:
            info = await asyncio.to_thread(yt.info_youtube, url, cfg)
        except Exception as e:  # noqa: BLE001
            LOG.warning("Falha ao consultar %s: %s", url, e)
            await editar(aviso, f"❌ Não consegui verificar esse vídeo.\n"
                                f"{html.escape(str(e))}{yt.dica_erro_youtube(e)}")
            continue

        duracao = info.get("duration") or 0
        if cfg.yt_duracao_max_min and duracao and duracao > cfg.yt_duracao_max_min * 60:
            await editar(
                aviso,
                f"⏱ <b>{html.escape(info.get('title') or url)}</b> tem "
                f"{yt.fmt_duracao(duracao)} e passa do limite de "
                f"{cfg.yt_duracao_max_min} min.",
            )
            continue

        texto, linhas_botoes, selecoes = yt.montar_opcoes(info, cfg)
        token = secrets.token_hex(4)
        if len(pendentes) > 200:
            pendentes.clear()
        pendentes[token] = {
            "url": url,
            "info": info,
            "user": update.effective_user.id,
            "chat": msg.chat_id,
            "selecoes": selecoes,
            "quando": time.time(),
        }
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton(etiqueta, callback_data=f"yt|{token}|{indice}")
             for etiqueta, indice in linha]
            for linha in linhas_botoes if linha
        ])
        LOG.info("Opções enviadas para %s (token %s)", url, token)
        await editar(aviso, texto, reply_markup=teclado)


async def botao_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: config_mod.Config = context.bot_data["cfg"]
    store: MinioStore | None = context.bot_data.get("minio")
    apagar: dict = context.bot_data.setdefault("apagar", {})

    consulta = update.callback_query
    partes = (consulta.data or "").split("|")
    pendentes: dict = context.bot_data.setdefault("yt_pendentes", {})
    pendente = pendentes.pop(partes[1], None) if len(partes) == 3 else None
    mensagem = consulta.message

    if pendente is None:
        await consulta.answer("⌛ Esta escolha expirou. Mande o link de novo.", show_alert=True)
        await editar(mensagem, "⌛ Opção expirada — mande o link do YouTube novamente.")
        return

    if not autorizado(update, cfg):
        await consulta.answer("🔒 Você não tem permissão para usar este bot.", show_alert=True)
        return

    if consulta.from_user.id != pendente["user"]:
        await consulta.answer("Esse download é de outro usuário. Mande o link você mesmo.",
                              show_alert=True)
        return

    selecao = pendente["selecoes"][int(partes[2])]
    await consulta.answer()
    try:
        await mensagem.edit_reply_markup(None)
    except Exception:  # noqa: BLE001
        pass

    titulo = pendente["info"].get("title") or "vídeo"
    titulo_html = html.escape(titulo)
    rotulo = selecao["rotulo"]
    LOG.info("Baixando %s (%s)", pendente["url"], rotulo)

    estado: dict = {"fase": "iniciando", "feito": 0, "total": 0}
    tmp = Path(tempfile.mkdtemp(prefix="yt-"))
    try:
        destino, _ = await rodar_com_progresso(
            mensagem, estado, titulo_html, rotulo, yt.baixar_youtube,
            INTERVALO_PROGRESSO, pendente["url"], tmp, selecao, cfg,
        )
        await entregar(mensagem, destino, selecao, pendente["info"],
                       cfg, store, apagar, consulta.from_user.id)
    except Exception as e:  # noqa: BLE001
        LOG.exception("Falha no download de %s", pendente["url"])
        await editar(
            mensagem,
            f"❌ Falha ao baixar <b>{titulo_html}</b>:\n"
            f"{html.escape(str(e))}{yt.dica_erro_youtube(e)}",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def botao_apagar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    consulta = update.callback_query
    partes = (consulta.data or "").split("|")
    apagar: dict = context.bot_data.setdefault("apagar", {})
    store: MinioStore | None = context.bot_data.get("minio")
    info = apagar.get(partes[1]) if len(partes) == 2 else None

    if info is None or store is None:
        await consulta.answer("Esse arquivo já foi removido.", show_alert=True)
        return
    if consulta.from_user.id != info["user"]:
        await consulta.answer("Só quem pediu o download pode apagar.", show_alert=True)
        return

    # Responde já: o delete no MinIO pode demorar e a query expira (~15 s).
    await consulta.answer("🗑 Apagando do MinIO…")
    apagar.pop(partes[1], None)
    await asyncio.to_thread(store.apagar, info["objeto"])
    try:
        await consulta.message.edit_reply_markup(None)
    except Exception:  # noqa: BLE001
        pass


async def receber(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: config_mod.Config = context.bot_data["cfg"]
    msg = update.effective_message
    if not autorizado(update, cfg):
        await msg.reply_text("🔒 Não autorizado.")
        LOG.warning("Mensagem de usuário não autorizado: %s", update.effective_user)
        return
    if msg.chat.type != "private" and not cfg.aceitar_grupos:
        return

    links = yt.achar_videos_youtube(msg.text or "")
    if links:
        await tratar_links(update, context, links)
        return

    await msg.reply_text(
        "Me mande um link de vídeo do YouTube (youtube.com, youtu.be, Shorts, etc.) "
        "que eu baixo e envio aqui."
    )


# ---------------------------------------------------------------------------
# Rotina de limpeza do MinIO
# ---------------------------------------------------------------------------

async def _janitor(app: Application) -> None:
    cfg: config_mod.Config = app.bot_data["cfg"]
    store: MinioStore | None = app.bot_data.get("minio")
    if store is None:
        return
    while True:
        await asyncio.sleep(3600)
        try:
            n = await asyncio.to_thread(store.limpar_antigos, PREFIXO_MINIO, cfg.minio_apagar_min)
            if n:
                LOG.info("Limpeza periódica do MinIO: %d objeto(s) removido(s).", n)
        except Exception as e:  # noqa: BLE001
            LOG.warning("Limpeza periódica do MinIO falhou: %s", e)


async def _post_init(app: Application) -> None:
    app.create_task(_janitor(app))


# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------

def configurar_log(cfg: config_mod.Config) -> None:
    nivel = getattr(logging, cfg.log_nivel, logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        arquivo = logging.handlers.RotatingFileHandler(
            cfg.log_arquivo, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"
        )
        handlers.append(arquivo)
    except Exception:  # noqa: BLE001 — sem permissão de arquivo não é fatal
        pass
    for h in handlers:
        h.setFormatter(fmt)

    logging.basicConfig(level=nivel, handlers=handlers, force=True)
    for nome in ("httpx", "httpcore", "urllib3", "botocore", "boto3", "s3transfer", "yt_dlp"):
        logging.getLogger(nome).setLevel(logging.WARNING)


def criar_store(cfg: config_mod.Config) -> MinioStore | None:
    if not cfg.minio_configurado():
        return None
    try:
        store = MinioStore(cfg)
        store.garantir_bucket()
        removidos = store.limpar_antigos(PREFIXO_MINIO, cfg.minio_apagar_min)
        LOG.info(
            "MinIO pronto em %s (bucket '%s'). %d objeto(s) antigo(s) removido(s).",
            store.endpoint, store.bucket, removidos,
        )
        return store
    except Exception:  # noqa: BLE001
        LOG.exception("MinIO configurado, mas inacessível: arquivos grandes ficarão indisponíveis.")
        return None


def main() -> None:
    cfg = config_mod.Config()
    configurar_log(cfg)

    ffmpeg = yt.caminho_ffmpeg() or "NÃO ENCONTRADO"
    LOG.info("Iniciando 'YouTube para Telegram'. Limite de envio direto: %d MB. ffmpeg: %s",
             cfg.max_envio_mb, ffmpeg)
    if cfg.yt_cookies:
        LOG.info("Usando cookies do YouTube: %s", cfg.yt_cookies)
    if not cfg.usuarios:
        LOG.warning("Nenhum usuário autorizado configurado: qualquer pessoa pode usar o bot.")

    store = criar_store(cfg)

    app = (
        Application.builder()
        .token(cfg.token)
        .concurrent_updates(True)
        .read_timeout(120)
        .write_timeout(600)
        .media_write_timeout(600)
        .build()
    )
    app.bot_data["cfg"] = cfg
    app.bot_data["minio"] = store
    app.bot_data["apagar"] = {}
    app.post_init = _post_init

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CallbackQueryHandler(botao_youtube, pattern=r"^yt\|"))
    app.add_handler(CallbackQueryHandler(botao_apagar, pattern=r"^del\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber))
    app.add_error_handler(tratar_erro)

    LOG.info("Bot no ar. Ctrl+C para encerrar.")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
