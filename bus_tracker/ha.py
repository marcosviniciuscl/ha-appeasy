"""Acesso ao Home Assistant: REST (estados, serviços) + WebSocket (eventos).

Dentro do App o Supervisor injeta SUPERVISOR_TOKEN e a API fica em
http://supervisor/core/api. Para testes fora do App, dá para apontar
HA_BASE / HA_WS / HA_TOKEN para a instância real.
"""

import base64
import json
import logging
import os
import socket
import ssl
import threading
import time
from urllib.parse import urlparse

import requests

log = logging.getLogger("bus_tracker.ha")

HA_BASE = os.environ.get("HA_BASE", "http://supervisor/core/api")
HA_WS = os.environ.get("HA_WS", "ws://supervisor/core/websocket")


def token():
    return (os.environ.get("HA_TOKEN") or os.environ.get("SUPERVISOR_TOKEN")
            or os.environ.get("HASSIO_TOKEN") or "")


def _headers():
    return {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}


def _url(caminho):
    return f"{HA_BASE}{caminho}"


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------

def estados():
    r = requests.get(_url("/states"), headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def estado(entity_id):
    try:
        r = requests.get(_url(f"/states/{entity_id}"), headers=_headers(), timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.debug(f"estado {entity_id}: {e}")
    return None


def definir_estado(entity_id, state, attributes=None):
    payload = {"state": state, "attributes": attributes or {}}
    r = requests.post(_url(f"/states/{entity_id}"), json=payload, headers=_headers(), timeout=8)
    return r.status_code


def remover_estado(entity_id):
    try:
        r = requests.delete(_url(f"/states/{entity_id}"), headers=_headers(), timeout=8)
        return r.status_code
    except Exception:
        return None


def chamar_servico(dominio, servico, dados):
    r = requests.post(_url(f"/services/{dominio}/{servico}"), json=dados, headers=_headers(), timeout=15)
    return r.status_code


def servicos():
    try:
        r = requests.get(_url("/services"), headers=_headers(), timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"não consegui listar serviços: {e}")
        return []


# ---------------------------------------------------------------------------
# WebSocket (cliente mínimo, só stdlib)
# ---------------------------------------------------------------------------

class _WsSocket:
    def __init__(self, url, timeout=20):
        u = urlparse(url)
        host = u.hostname
        porta = u.port or (443 if u.scheme in ("wss", "https") else 80)
        caminho = u.path or "/websocket"
        if u.query:
            caminho += "?" + u.query
        self.sock = socket.create_connection((host, porta), timeout=timeout)
        if u.scheme in ("wss", "https"):
            ctx = ssl.create_default_context()
            self.sock = ctx.wrap_socket(self.sock, server_hostname=host)
        chave = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {caminho} HTTP/1.1\r\nHost: {host}:{porta}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {chave}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            pedaco = self.sock.recv(4096)
            if not pedaco:
                raise ConnectionError("handshake WebSocket sem resposta")
            resp += pedaco
        if b" 101 " not in resp.split(b"\r\n")[0]:
            raise ConnectionError(f"handshake recusado: {resp.split(chr(13).encode())[0]!r}")
        self.sock.settimeout(5)

    def enviar(self, dados, opcode=1):
        if isinstance(dados, str):
            dados = dados.encode()
        cab = bytes([0x80 | opcode])
        m = os.urandom(4)
        n = len(dados)
        if n < 126:
            cab += bytes([0x80 | n])
        elif n < 65536:
            cab += bytes([0x80 | 126]) + n.to_bytes(2, "big")
        else:
            cab += bytes([0x80 | 127]) + n.to_bytes(8, "big")
        mascara = bytes(b ^ m[i % 4] for i, b in enumerate(dados))
        self.sock.sendall(cab + m + mascara)

    def _ler_exato(self, n):
        buf = b""
        while len(buf) < n:
            pedaco = self.sock.recv(n - len(buf))
            if not pedaco:
                raise ConnectionError("conexão fechada")
            buf += pedaco
        return buf

    def receber(self):
        """Devolve (opcode, payload_bytes) ou (None, None) em timeout."""
        try:
            h = self._ler_exato(2)
        except socket.timeout:
            return None, None
        opcode = h[0] & 0x0F
        mascarado = h[1] & 0x80
        n = h[1] & 0x7F
        if n == 126:
            n = int.from_bytes(self._ler_exato(2), "big")
        elif n == 127:
            n = int.from_bytes(self._ler_exato(8), "big")
        mascara = self._ler_exato(4) if mascarado else None
        dados = self._ler_exato(n) if n else b""
        if mascara:
            dados = bytes(b ^ mascara[i % 4] for i, b in enumerate(dados))
        return opcode, dados

    def fechar(self):
        try:
            self.enviar(b"", opcode=8)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class Escutador(threading.Thread):
    """Escuta eventos do HA (por padrão, ações das notificações do app)."""

    def __init__(self, ao_evento, eventos=("mobile_app_notification_action",)):
        super().__init__(daemon=True, name="ha-ws")
        self.ao_evento = ao_evento
        self.eventos = list(eventos)
        self.parar = threading.Event()
        self.conectado = False
        self.ultimo_evento = 0.0

    def run(self):
        espera = 5
        while not self.parar.is_set():
            try:
                self._sessao()
                espera = 5
            except Exception as e:
                self.conectado = False
                log.warning(f"WebSocket do HA caiu ({e}); reconecto em {espera}s")
                self.parar.wait(espera)
                espera = min(60, espera * 2)

    def _sessao(self):
        ws = _WsSocket(HA_WS)
        try:
            ws.sock.settimeout(15)
            _, bruto = ws.receber()
            ws.enviar(json.dumps({"type": "auth", "access_token": token()}))
            _, bruto = ws.receber()
            resp = json.loads(bruto)
            if resp.get("type") != "auth_ok":
                raise ConnectionError(f"auth falhou: {resp}")
            for i, ev in enumerate(self.eventos, start=1):
                ws.enviar(json.dumps({"id": i, "type": "subscribe_events", "event_type": ev}))
            self.conectado = True
            log.info(f"Escutando eventos do HA: {', '.join(self.eventos)}")
            ultimo_ping = time.time()
            while not self.parar.is_set():
                opcode, bruto = ws.receber()
                if opcode is None:
                    if time.time() - ultimo_ping > 25:
                        ws.enviar(b"", opcode=9)
                        ultimo_ping = time.time()
                    continue
                if opcode == 9:  # ping
                    ws.enviar(bruto, opcode=10)
                    continue
                if opcode == 8:
                    raise ConnectionError("servidor fechou")
                if opcode != 1:
                    continue
                try:
                    msg = json.loads(bruto)
                except Exception:
                    continue
                if msg.get("type") == "event":
                    self.ultimo_evento = time.time()
                    try:
                        self.ao_evento(msg["event"])
                    except Exception as e:
                        log.error(f"erro ao tratar evento: {e}")
        finally:
            self.conectado = False
            ws.fechar()
