# -*- coding: utf-8 -*-
"""Configuração do App, lida de /data/options.json (Home Assistant).

Fora do Home Assistant, dá para apontar para outro arquivo com a variável de
ambiente YT_OPTIONS (útil para testar no PC).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DIR_DADOS = Path(os.environ.get("YT_DATA_DIR", "/data"))
ARQUIVO_OPCOES = Path(os.environ.get("YT_OPTIONS", str(DIR_DADOS / "options.json")))


class Config:
    def __init__(self, caminho: Path | None = None) -> None:
        self.caminho = Path(caminho) if caminho else ARQUIVO_OPCOES
        bruto = self._ler(self.caminho)

        # --- Telegram -------------------------------------------------------
        self.token: str = str(bruto.get("telegram_token") or "").strip()
        self.usuarios: set[int] = {int(u) for u in (bruto.get("usuarios_autorizados") or [])}
        self.aceitar_grupos: bool = bool(bruto.get("aceitar_grupos", False))

        # --- YouTube --------------------------------------------------------
        yt = bruto.get("youtube") or {}
        self.yt_ativo: bool = bool(yt.get("ativo", True))
        self.yt_altura_maxima: int = int(yt.get("altura_maxima", 1080))
        self.yt_duracao_max_min: int = int(yt.get("duracao_maxima_min", 120))
        self.yt_mp3_kbps: int = int(yt.get("mp3_bitrate_kbps", 192))
        self.yt_cookies: str = self._resolver_cookies(yt.get("cookies") or "")

        # --- Envio direto pelo Telegram ------------------------------------
        tg = bruto.get("telegram") or {}
        self.max_envio_mb: int = int(tg.get("tamanho_maximo_mb", 50))

        # --- MinIO ----------------------------------------------------------
        mn = bruto.get("minio") or {}
        self.minio_ativo: bool = bool(mn.get("ativo", False))
        self.minio_endpoint: str = str(mn.get("endpoint") or "").strip()
        self.minio_access: str = str(mn.get("access_key") or "").strip()
        self.minio_secret: str = str(mn.get("secret_key") or "").strip()
        self.minio_bucket: str = str(mn.get("bucket") or "youtube-telegram").strip()
        self.minio_secure: bool = bool(mn.get("secure", True))
        self.minio_regiao: str = str(mn.get("regiao") or "").strip()
        self.minio_expira_min: int = int(mn.get("url_expira_min", 60))
        self.minio_apagar_min: int = int(mn.get("apagar_apos_min", 70))

        # --- Log ------------------------------------------------------------
        lg = bruto.get("log") or {}
        self.log_nivel: str = str(lg.get("nivel", "INFO") or "INFO").upper()
        self.log_arquivo: str = str(DIR_DADOS / "youtube-telegram.log")

        if not self.token:
            sys.exit("ERRO: 'telegram_token' está vazio nas opções do App.")

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _ler(caminho: Path) -> dict:
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except FileNotFoundError:
            sys.exit(
                f"ERRO: opções não encontradas em {caminho}.\n"
                "Rode este programa pelo Home Assistant ou defina YT_OPTIONS "
                "apontando para um options.json."
            )
        except json.JSONDecodeError as e:
            sys.exit(f"ERRO: options.json inválido: {e}")

    @staticmethod
    def _resolver_cookies(valor: str) -> str:
        """Usa o caminho informado ou procura cookies.txt em locais conhecidos."""
        candidatos: list[str] = []
        if valor and valor.strip():
            candidatos.append(valor.strip())
        candidatos += [str(DIR_DADOS / "cookies.txt"), "/share/youtube-cookies.txt"]
        for c in candidatos:
            if c and Path(c).is_file():
                return c
        return ""

    @property
    def max_envio_bytes(self) -> int:
        return self.max_envio_mb * 1024 * 1024

    def minio_configurado(self) -> bool:
        return bool(
            self.minio_ativo
            and self.minio_endpoint
            and self.minio_access
            and self.minio_secret
        )
