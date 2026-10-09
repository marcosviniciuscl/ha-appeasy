"""Aprende o percurso real dos ônibus.

Os motoristas nem sempre seguem o traçado oficial que o sistema tem registrado.
Este módulo guarda, com o tempo, amostras de GPS dos veículos por
linha/itinerário numa grelha geográfica (~22 m) com contagem de visitas e
reconstrói o **percurso mais percorrido** — o corredor que os ônibus de fato
usam.

Como o percurso real é montado
-----------------------------
O traçado oficial serve de "espinha": caminhamos por ele a cada `passo_m` e,
em cada ponto, escolhemos a célula **mais visitada** num raio. O resultado é uma
linha ordenada que segue o caminho real e, onde os motoristas desviam, desgruda
do oficial — permitindo comparar "sistema" × "real" no mapa.

Persistência: `<DIR_DADOS>/percursos.json`.
"""

import json
import logging
import os
import tempfile
import threading
import time

import geo

log = logging.getLogger("bus_tracker.percurso")

DIR_DADOS = os.environ.get("DIR_DADOS", "/data")
ARQ = os.path.join(DIR_DADOS, "percursos.json")

CELULA_GRAUS = 0.0002            # ~22 m por célula
METROS_GRAU_LAT = 111320.0
TTL_AMOSTRA = 45 * 24 * 3600     # descarta células sem visita em 45 dias
MAX_CELULAS = 6000               # por linha/itinerário
SALVAR_A_CADA = 300              # segundos

_lock = threading.RLock()
_dados = {}                      # "SIGLA|cod_it" -> {"i,j": [n, ts]}
_ultimo_salvo = 0.0
_sujo = False
_real_cache = {}                 # "SIGLA|cod_it" -> (ts, info|None)


def _norm(s):
    return (s or "").upper().lstrip("0") or "0"


def _chave(sigla, cod_it):
    return f"{_norm(sigla)}|{cod_it}"


def _cel(lat, lon):
    return int(round(lat / CELULA_GRAUS)), int(round(lon / CELULA_GRAUS))


def carregar():
    """Carrega as amostras salvas (chamado uma vez ao iniciar o App)."""
    global _dados
    try:
        with open(ARQ, encoding="utf-8") as f:
            bruto = json.load(f)
        if isinstance(bruto, dict):
            with _lock:
                _dados = {k: v for k, v in bruto.items() if isinstance(v, dict)}
            total = sum(len(v) for v in _dados.values())
            log.info("percurso real: %d linha(s), %d célula(s)", len(_dados), total)
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("percursos.json inválido (%s); recomeçando", e)


def registrar(sigla, cod_it, lat, lon):
    """Conta uma visita do veículo à célula em que ele está."""
    global _sujo
    try:
        i, j = _cel(float(lat), float(lon))
    except (TypeError, ValueError):
        return
    agora = time.time()
    chave = _chave(sigla, cod_it)
    with _lock:
        celulas = _dados.setdefault(chave, {})
        c = celulas.get(f"{i},{j}")
        if c:
            c[0] += 1
            c[1] = agora
        else:
            celulas[f"{i},{j}"] = [1, agora]
        if len(celulas) > MAX_CELULAS:
            _podar(celulas, MAX_CELULAS)
        _sujo = True
    _talvez_salvar()


def _podar(celulas, limite):
    """Remove as células menos visitadas/mais antigas quando estoura o limite."""
    itens = sorted(celulas.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    for k, _ in itens[:max(0, len(celulas) - limite)]:
        celulas.pop(k, None)


def _talvez_salvar():
    global _sujo, _ultimo_salvo
    if not _sujo or (time.time() - _ultimo_salvo) < SALVAR_A_CADA:
        return
    salvar()


def salvar(force=False):
    global _sujo, _ultimo_salvo
    with _lock:
        if not (_sujo or force):
            return
        _limpar()
        dados = json.loads(json.dumps(_dados))
        _sujo = False
        _ultimo_salvo = time.time()
    try:
        os.makedirs(DIR_DADOS, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=DIR_DADOS, prefix=".percursos-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, ARQ)
    except Exception as e:
        log.warning("não salvei percursos.json: %s", e)


def _limpar():
    """Descarta células sem visita há mais de TTL_AMOSTRA."""
    limite = time.time() - TTL_AMOSTRA
    for chave in list(_dados):
        celulas = _dados.get(chave) or {}
        for k, c in list(celulas.items()):
            if c[1] < limite:
                celulas.pop(k, None)
        if not celulas:
            _dados.pop(chave, None)


def _celulas(chave):
    with _lock:
        return dict(_dados.get(chave) or {})


def limpar_cache():
    with _lock:
        _real_cache.clear()


def resumo():
    """Quantas amostras há por linha/itinerário (para diagnóstico)."""
    with _lock:
        return {k: {"celulas": len(v), "amostras": sum(c[0] for c in v.values())}
                for k, v in _dados.items()}


def percurso_real(rota, sigla, cod_it, passo_m=60, raio_m=300,
                  min_amostras=25, ttl=1200):
    """Reconstrói o percurso mais percorrido a partir do traçado oficial.

    `rota` é uma `geo.Rota` (o traçado do sistema). Devolve
    `{"pontos", "amostras", "desvio_max_m", "celulas"}` ou `None` quando ainda
    não há amostras suficientes. Cacheado por `ttl` (20 min).
    """
    if rota is None or not getattr(rota, "pts", None):
        return None
    chave = _chave(sigla, cod_it)
    agora = time.time()
    cache = _real_cache.get(chave)
    if cache and (agora - cache[0]) < ttl:
        return cache[1]
    celulas = _celulas(chave)
    amostras = sum(c[0] for c in celulas.values())
    if not celulas or amostras < min_amostras:
        return None

    grade = {}
    for k, c in celulas.items():
        try:
            i, j = (int(x) for x in k.split(","))
        except ValueError:
            continue
        grade[(i, j)] = c
    r_cel = max(1, int(raio_m / (CELULA_GRAUS * METROS_GRAU_LAT)) + 1)

    n = max(2, int(rota.comprimento // passo_m) + 1)
    pontos, desvio = [], 0.0
    for idx in range(n + 1):
        s = min(rota.comprimento, idx * passo_m)
        ref = rota.ponto_em(s)
        if not ref:
            continue
        ci, cj = _cel(ref[0], ref[1])
        melhor = None
        for di in range(-r_cel, r_cel + 1):
            for dj in range(-r_cel, r_cel + 1):
                c = grade.get((ci + di, cj + dj))
                if not c:
                    continue
                lat = (ci + di) * CELULA_GRAUS
                lon = (cj + dj) * CELULA_GRAUS
                d = geo.haversine(ref, (lat, lon))
                if d > raio_m:
                    continue
                if melhor is None or c[0] > melhor[2] or (c[0] == melhor[2] and d < melhor[3]):
                    melhor = (lat, lon, c[0], d)
        if melhor:
            pontos.append([round(melhor[0], 5), round(melhor[1], 5)])
            if melhor[3] > desvio:
                desvio = melhor[3]
    if len(pontos) < 3:
        return None
    info = {"pontos": pontos, "amostras": amostras,
            "desvio_max_m": round(desvio), "celulas": len(celulas)}
    _real_cache[chave] = (agora, info)
    return info
