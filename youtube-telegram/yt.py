# -*- coding: utf-8 -*-
"""Funções do YouTube (yt-dlp): links, opções, download e progresso.

Baseado na lógica já validada do bot do Holyrics, adaptada para o App.
"""
from __future__ import annotations

import html
import logging
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

LOG = logging.getLogger("youtube-telegram.yt")

RE_YOUTUBE = re.compile(
    r"(?:https?://)?(?:(?:www|m|music)\.)?"
    r"(?:youtube\.com/(?:watch\?[^\s]*?\bv=|shorts/|live/|embed/|v/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)

_FFMPEG: str | None | bool = False  # False = ainda não procurado


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def fmt_bytes(n: int | float) -> str:
    n = float(n or 0)
    if n <= 0:
        return "0 B"
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            if unidade == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unidade}".replace(".", ",")
        n /= 1024.0
    return f"{n:.1f} GB"


def fmt_duracao(segundos: float | int | None) -> str:
    if not segundos:
        return "?"
    segundos = int(segundos)
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def slug(texto: str) -> str:
    """Nome de arquivo/objeto seguro (ASCII, sem espaços)."""
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = texto.encode("ascii", "ignore").decode("ascii")
    base = Path(texto).stem
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-") or "arquivo"
    suf = re.sub(r"[^A-Za-z0-9.]+", "", Path(texto).suffix)
    return (base[:80] + suf) or "arquivo"


def caminho_ffmpeg() -> str | None:
    global _FFMPEG
    if _FFMPEG is False:
        achado = shutil.which("ffmpeg")
        _FFMPEG = achado if achado else None
    return _FFMPEG  # type: ignore[return-value]


def ffmpeg_disponivel() -> bool:
    return caminho_ffmpeg() is not None


# ---------------------------------------------------------------------------
# Links e metadados
# ---------------------------------------------------------------------------

def achar_videos_youtube(texto: str) -> list[str]:
    """Extrai links de vídeo do YouTube de um texto (sem repetir)."""
    vistos: set[str] = set()
    urls: list[str] = []
    for achado in RE_YOUTUBE.finditer(texto or ""):
        vid = achado.group(1)
        if vid not in vistos:
            vistos.add(vid)
            urls.append(f"https://www.youtube.com/watch?v={vid}")
    return urls


def opcoes_ytdlp(cfg) -> dict:
    opts: dict = {"quiet": True, "no_warnings": True, "noplaylist": True}
    if getattr(cfg, "yt_cookies", ""):
        opts["cookiefile"] = cfg.yt_cookies
    ffmpeg = caminho_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    return opts


def info_youtube(url: str, cfg) -> dict:
    """Consulta os dados do vídeo (título, duração, formatos disponíveis)."""
    import yt_dlp

    opts = opcoes_ytdlp(cfg)
    opts["skip_download"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


# ---------------------------------------------------------------------------
# Montagem das opções (2 vídeo + 2 áudio)
# ---------------------------------------------------------------------------

def _tamanho_estimado(f: dict, duracao: float | None) -> int:
    tam = f.get("filesize") or f.get("filesize_approx")
    if not tam and f.get("tbr") and duracao:
        tam = float(f["tbr"]) * 1000 / 8 * duracao
    return int(tam or 0)


def _formatos_audio(formatos: list[dict]) -> list[dict]:
    return [f for f in formatos if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]


def _formatos_video(formatos: list[dict]) -> list[dict]:
    return [f for f in formatos if f.get("height") and f.get("vcodec") not in (None, "none")]


def estimativa_video(formatos: list[dict], altura: int, duracao: float | None) -> int:
    videos = [f for f in _formatos_video(formatos) if int(f["height"]) <= altura]
    if not videos:
        return 0
    audios = _formatos_audio(formatos)
    total = _tamanho_estimado(max(videos, key=lambda f: int(f["height"])), duracao)
    if audios:
        total += _tamanho_estimado(max(audios, key=lambda f: _tamanho_estimado(f, duracao)), duracao)
    return total


def estimativa_audio(formatos: list[dict], duracao: float | None) -> int:
    return max((_tamanho_estimado(f, duracao) for f in _formatos_audio(formatos)), default=0)


def montar_opcoes(info: dict, cfg) -> tuple[str, list[list[tuple[str, int]]], list[dict]]:
    """Monta o texto e os botões (2 de vídeo + 2 de áudio) para o vídeo."""
    titulo = info.get("title") or "vídeo"
    canal = info.get("uploader") or info.get("channel") or "?"
    duracao = info.get("duration")
    formatos = info.get("formats") or []
    com_ffmpeg = ffmpeg_disponivel()

    alturas = sorted(
        {int(f["height"]) for f in _formatos_video(formatos) if int(f["height"]) <= cfg.yt_altura_maxima},
        reverse=True,
    )
    escolhidas: list[int | None] = []
    if alturas:
        escolhidas.append(alturas[0])
        menor = next((h for h in alturas[1:] if h <= alturas[0] * 0.75), None)
        escolhidas.append(menor if menor else (alturas[1] if len(alturas) > 1 else None))
    else:
        escolhidas = [None]

    selecoes: list[dict] = []
    linha_video: list[tuple[str, int]] = []
    for altura in escolhidas:
        if altura is None:
            if not linha_video:
                formato = "bestvideo+bestaudio/best" if com_ffmpeg else "best"
                rotulo = "Melhor disponível"
                estimativa = 0
            else:
                continue
        else:
            altura = int(altura)
            if com_ffmpeg:
                formato = (
                    f"bestvideo[height<={altura}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height<={altura}]+bestaudio/best[height<={altura}]"
                )
            else:
                formato = f"best[height<={altura}][ext=mp4]/best[height<={altura}]"
            rotulo = f"{altura}p"
            estimativa = estimativa_video(formatos, altura, duracao)
        indice = len(selecoes)
        selecoes.append({
            "formato": formato, "mp3": False, "rotulo": rotulo,
            "tipo": "video", "altura": altura,
        })
        etiqueta = f"🎬 {rotulo}" + (f" · ~{fmt_bytes(estimativa)}" if estimativa else "")
        linha_video.append((etiqueta, indice))

    estim_audio = estimativa_audio(formatos, duracao)
    if com_ffmpeg:
        # O áudio é sempre salvo em MP3 (formato preferido do Holyrics).
        pares_audio = [
            ({"formato": "bestaudio/best", "mp3": True, "kbps": cfg.yt_mp3_kbps,
              "rotulo": f"MP3 {cfg.yt_mp3_kbps} kbps", "tipo": "audio"},
             f"🎵 MP3 {cfg.yt_mp3_kbps}k"),
            ({"formato": "bestaudio/best", "mp3": True, "kbps": 128,
              "rotulo": "MP3 128 kbps", "tipo": "audio"},
             "🎵 MP3 128k (leve)"),
        ]
    else:
        pares_audio = [
            ({"formato": "bestaudio[ext=m4a]/bestaudio", "mp3": False, "rotulo": "Melhor áudio (m4a)", "tipo": "audio"},
             "🎵 Melhor áudio"),
            ({"formato": "bestaudio[abr<=64]/bestaudio", "mp3": False, "rotulo": "Áudio leve (m4a)", "tipo": "audio"},
             f"🎵 Leve {fmt_bytes(estim_audio // 4) if estim_audio else '~64k'}"),
        ]
    linha_audio: list[tuple[str, int]] = []
    for selecao, etiqueta in pares_audio:
        indice = len(selecoes)
        selecoes.append(selecao)
        if estim_audio and selecao == pares_audio[0][0]:
            etiqueta += f" · ~{fmt_bytes(estim_audio)}"
        linha_audio.append((etiqueta, indice))

    linhas = [
        f"🎬 <b>{html.escape(titulo)}</b>",
        f"👤 {html.escape(str(canal))} · ⏱ {fmt_duracao(duracao)}",
        "Escolha o formato:",
    ]
    if not com_ffmpeg:
        linhas.append("⚠️ ffmpeg não encontrado: sem MP3 e sem juntar vídeo+áudio.")

    return "\n".join(linhas), [linha_video, linha_audio], selecoes


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def localizar_arquivo_baixado(pasta: Path, info: dict) -> Path | None:
    """Descobre o arquivo final gerado pelo yt-dlp dentro da pasta temporária."""
    candidatos = [
        p for p in pasta.rglob("*")
        if p.is_file()
        and not p.name.endswith((".part", ".ytdl", ".temp"))
        and not re.search(r"\.f\d+\.\w+$", p.name)
    ]
    if not candidatos:
        return None
    for pedido in (info.get("requested_downloads") or []):
        caminho = Path(pedido.get("filepath") or "")
        if caminho and caminho.exists():
            return caminho
        if caminho:
            for c in candidatos:
                if c.with_suffix("") == caminho.with_suffix(""):
                    return c
    return max(candidatos, key=lambda p: p.stat().st_size)


def baixar_youtube(estado: dict, url: str, pasta: Path, selecao: dict, cfg) -> tuple[Path, dict]:
    """Baixa (e converte, se MP3) o vídeo. Roda em thread; informa o progresso via `estado`."""
    import yt_dlp

    tmp = Path(tempfile.mkdtemp(prefix="yt-dl-"))

    def hook(d):
        status = d.get("status")
        if status == "downloading":
            estado.update(
                fase="baixando",
                feito=d.get("downloaded_bytes") or 0,
                total=d.get("total_bytes") or d.get("total_bytes_estimate") or 0,
                vel=d.get("speed") or 0,
                eta=d.get("eta") or 0,
            )
        elif status == "finished":
            estado.update(fase="processando", vel=0, eta=0)

    def hook_pp(d):
        if d.get("status") == "started":
            estado.update(fase="convertendo", pp=d.get("postprocessor"))

    opts = opcoes_ytdlp(cfg)
    opts.update({
        "outtmpl": str(tmp / "%(title).120B.%(ext)s"),
        "format": selecao["formato"],
        "progress_hooks": [hook],
        "postprocessor_hooks": [hook_pp],
        "noprogress": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "trim_file_name": 120,
        "windowsfilenames": True,
    })
    if selecao["tipo"] == "video":
        opts["merge_output_format"] = "mp4"
    if selecao.get("mp3"):
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": str(selecao.get("kbps") or cfg.yt_mp3_kbps),
        }]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        estado["fase"] = "salvando"
        origem = localizar_arquivo_baixado(tmp, info)
        if origem is None:
            raise RuntimeError("o download terminou mas nenhum arquivo foi encontrado")
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / slug(origem.name)
        if destino.exists():
            destino = pasta / f"{destino.stem}-{abs(hash(origem.name)) % 10_000}{destino.suffix}"
        shutil.move(str(origem), str(destino))
        return destino, info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Textos de progresso e erro
# ---------------------------------------------------------------------------

def texto_progresso_yt(estado: dict, titulo_html: str, rotulo: str) -> str:
    fase = estado.get("fase", "iniciando")
    if fase == "baixando":
        feito = estado.get("feito") or 0
        total = estado.get("total") or 0
        pct = int(feito * 100 / total) if total else 0
        partes = [f"{pct}%", fmt_bytes(feito) + (f" de {fmt_bytes(total)}" if total else "")]
        if estado.get("vel"):
            partes.append(f"{fmt_bytes(int(estado['vel']))}/s")
        if estado.get("eta"):
            partes.append(f"faltam {fmt_duracao(estado['eta'])}")
        return f"⬇️ Baixando <b>{titulo_html}</b> ({rotulo})\n" + " · ".join(partes)
    if fase == "convertendo":
        pp = (estado.get("pp") or "").lower()
        if "extractaudio" in pp:
            return f"🎧 Convertendo para {rotulo}…\n<b>{titulo_html}</b>"
        if "merge" in pp:
            return f"🎬 Juntando vídeo + áudio…\n<b>{titulo_html}</b>"
        return f"⚙️ Processando <b>{titulo_html}</b>…"
    if fase == "processando":
        return f"⚙️ Finalizando o download de <b>{titulo_html}</b>…"
    if fase == "salvando":
        return f"📦 Preparando <b>{titulo_html}</b>…"
    return f"⏳ Preparando <b>{titulo_html}</b>…"


def dica_erro_youtube(e: Exception) -> str:
    texto = str(e)
    baixo = texto.lower()
    if "sign in to confirm" in baixo or "not a bot" in baixo or "cookies" in baixo:
        return (
            "\n\n👉 O YouTube pediu verificação de robô. Coloque um arquivo de cookies no "
            "formato Netscape em <code>/share/youtube-cookies.txt</code> (ou aponte o caminho "
            "na opção <code>youtube.cookies</code>) e tente de novo."
        )
    if "ffmpeg" in baixo:
        return "\n\n👉 O ffmpeg não foi encontrado dentro do App."
    if "unavailable" in baixo or "private" in baixo:
        return "\n\n👉 O vídeo parece privado ou indisponível."
    if "unsupported url" in baixo:
        return "\n\n👉 Esse link não é de um vídeo do YouTube."
    return ""
