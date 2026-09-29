"""Rotas de caminhada por ruas (OSRM) com cache e fallback para linha reta.

O roteamento é feito pelo próprio App (servidor), então o celular não precisa
falar com o OSRM. Se o OSRM estiver fora do ar, cai para linha reta com fator
de rota.
"""

import logging
import threading
import time

import requests

import geo

log = logging.getLogger("bus_tracker.rotas")

OSRM_BASE = "https://routing.openstreetmap.de/routed-foot"
TIMEOUT = 8
FATOR_FALLBACK = 1.3
TTL = 6 * 3600

_base = OSRM_BASE
_cache = {}
_lock = threading.Lock()


def configurar(base=None):
    global _base
    if base:
        _base = base.strip().rstrip("/")
        _cache.clear()


def _perfil():
    # o roteador a pé (FOSSGIS routed-foot) ignora o perfil na URL; o project-osrm
    # só tem "driving". Então escolhe pelo servidor configurado.
    return "foot" if "routed-foot" in _base else "driving"


def _chave(a, b):
    # ~11 m de precisão: aumenta muito o acerto do cache enquanto a pessoa anda
    return (round(a[0], 4), round(a[1], 4), round(b[0], 5), round(b[1], 5))


def _osrm(origem, destino):
    # OSRM espera lon,lat. Usa roteamento a pé (distância/geometria por ruas,
    # muito melhor que "driving" para caminhada).
    coords = f"{origem[1]},{origem[0]};{destino[1]},{destino[0]}"
    url = f"{_base}/route/v1/{_perfil()}/{coords}?overview=full&geometries=geojson"
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if d.get("code") != "Ok" or not d.get("routes"):
        return None
    rota = d["routes"][0]
    dist = float(rota.get("distance") or 0)
    pts = [[c[1], c[0]] for c in (rota.get("geometry", {}).get("coordinates") or [])]
    if dist <= 0 or len(pts) < 2:
        return None
    return {"dist_m": dist, "pontos": pts, "fonte": "ruas"}


def caminhada(origem, destino, forcar=False):
    """{dist_m, pontos:[[lat,lon]], fonte}. Cacheado por 6 h."""
    if not origem or not destino:
        return None
    chave = _chave(origem, destino)
    with _lock:
        c = _cache.get(chave)
    if c and not forcar and (time.time() - c[0]) < TTL:
        return c[1]
    info = None
    try:
        info = _osrm(origem, destino)
    except Exception as e:
        log.debug(f"OSRM falhou ({origem}->{destino}): {e}")
    if not info:
        dist = geo.haversine(origem, destino) * FATOR_FALLBACK
        info = {"dist_m": dist, "pontos": [list(origem), list(destino)], "fonte": "reta"}
    with _lock:
        _cache[chave] = (time.time(), info)
    return info
