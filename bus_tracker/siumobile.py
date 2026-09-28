"""Cliente da API do SIUMobile (TACOM / CIT-Siu).

O mesmo backend atende várias cidades ("praças"). A cidade é escolhida nas
opções do App; também dá para informar URL/praça/pacote manualmente para
qualquer outra cidade que use o SIUMobile.

Endpoints usados (verificados em Feira de Santana):
  buscarLinhas/retornoJSONListaLinhas                    -> todas as linhas
  V3/buscarParadasPorLinha/{cod}/0/{praca}/retornoJSON   -> paradas ordenadas
  buscarParadasProximas/{lon}/{lat}/{raio}/retornoJSON   -> paradas próximas (x/y)
  V3/buscarPrevisoes/{codParada}/false/0/{praca}/...     -> previsões ativas
  V3/retornaVeiculosMapa/{codIt}/0/{praca}/...Veiculos   -> veículos ao vivo
  V3/buscarItinerario/{codIt}/0/{praca}/retornoJSON      -> traçado (X=lon, Y=lat)
"""

import json
import logging
import re
import threading
import time

import requests

log = logging.getLogger("bus_tracker.api")

TIMEOUT = 12

# Cidades/praças conhecidas do SIUMobile. `base` já inclui o caminho da API.
CIDADES = {
    "feira_de_santana": {
        "nome": "Feira de Santana (BA)",
        "base": "http://fsa.siumobile.com.br:6060/siumobile-ws-v01/rest/ws",
        "praca": "null",
        "pacote": "com.tacom.siumobilefsa",
        "fuso": "America/Bahia",
        "centro": [-12.2664, -38.9663],
    },
    "belo_horizonte": {
        "nome": "Belo Horizonte (MG)",
        "base": "http://bhz.siumobile.com.br:6060/siumobiletacomapp/siumobile-ws-v01/rest/ws",
        "praca": "BHZ",
        "pacote": "com.tacom.siumobilebh",
        "fuso": "America/Sao_Paulo",
        "centro": [-19.9167, -43.9345],
    },
}

CIDADE_PADRAO = "feira_de_santana"

_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-G780G Build/TP1A.220624.014; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/145.0.7632.159 Mobile Safari/537.36"
)

_estado = {
    "cidade": CIDADE_PADRAO,
    "base": CIDADES[CIDADE_PADRAO]["base"],
    "praca": CIDADES[CIDADE_PADRAO]["praca"],
    "pacote": CIDADES[CIDADE_PADRAO]["pacote"],
    "centro": CIDADES[CIDADE_PADRAO]["centro"],
}
_lock = threading.Lock()

_linhas_cache = {"ts": 0.0, "dados": []}
LINHAS_TTL = 1800  # 30 min
_rota_cache = {}


def cidades():
    """Mapa chave -> nome das cidades embutidas."""
    return {chave: info["nome"] for chave, info in CIDADES.items()}


def configurar(cidade=None, base=None, praca=None, pacote=None):
    """Define a cidade (e overrides) usada nas próximas requisições.

    `cidade` pode ser uma chave de CIDADES ou `"custom"` (nesse caso informe
    `base`/`praca`/`pacote`).
    """
    with _lock:
        if cidade:
            info = CIDADES.get(cidade)
            if info:
                _estado.update(cidade=cidade, base=info["base"], praca=info["praca"],
                               pacote=info["pacote"], centro=info.get("centro"))
            else:
                _estado.update(cidade="custom", centro=None)
        if base:
            _estado["base"] = base.strip().rstrip("/")
            if _estado["cidade"] not in CIDADES:
                _estado["cidade"] = "custom"
        if praca is not None and str(praca).strip():
            _estado["praca"] = str(praca).strip()
        if pacote:
            _estado["pacote"] = pacote.strip()
        # troca de cidade invalida os caches
        _linhas_cache.update(ts=0.0, dados=[])
        _rota_cache.clear()
    log.info("SIUMobile: cidade=%s base=%s praca=%s pacote=%s",
             _estado["cidade"], _estado["base"], _estado["praca"], _estado["pacote"])


def cidade_atual():
    info = CIDADES.get(_estado["cidade"], {})
    praca = _estado["praca"]
    nome = info.get("nome") or (praca if praca not in ("", "null") else "Personalizada")
    return {
        "chave": _estado["cidade"],
        "nome": nome,
        "base": _estado["base"],
        "praca": _estado["praca"],
        "pacote": _estado["pacote"],
        "centro": info.get("centro") or _estado.get("centro"),
    }


def fuso_da_cidade(cidade=None):
    info = CIDADES.get(cidade or _estado["cidade"], {})
    return info.get("fuso")


def _praca():
    return _estado["praca"]


def norm_sigla(s):
    return (s or "").upper().lstrip("0") or "0"


def _jsonp(texto, nome):
    m = re.search(rf"{re.escape(nome)}\((.*)\)\s*$", texto, re.DOTALL)
    if not m:
        raise ValueError(f"resposta JSONP inválida ({nome})")
    return json.loads(m.group(1))


def _get(caminho):
    cabecalhos = {
        "User-Agent": _UA,
        "X-Requested-With": _estado["pacote"],
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate",
    }
    r = requests.get(f"{_estado['base']}{caminho}", headers=cabecalhos, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


# ---------------------------------------------------------------------------
# Linhas
# ---------------------------------------------------------------------------

def buscar_linhas(forcar=False):
    """Lista de {'cod', 'sgl', 'nom'} de todas as linhas."""
    if not forcar and _linhas_cache["dados"] and (time.time() - _linhas_cache["ts"]) < LINHAS_TTL:
        return _linhas_cache["dados"]
    dados = _jsonp(_get("/buscarLinhas/retornoJSONListaLinhas"), "retornoJSONListaLinhas")
    linhas = []
    for token in re.findall(r"\{[^{}]+\}", ",".join(dados.get("linhas", []))):
        try:
            linhas.append(json.loads(re.sub(r"'([^']*)'", r'"\1"', token)))
        except Exception:
            continue
    # normaliza cod para int quando possível
    for l in linhas:
        try:
            l["cod"] = int(l["cod"])
        except Exception:
            pass
    _linhas_cache.update(ts=time.time(), dados=linhas)
    return linhas


def linha_por_sigla(sigla):
    alvo = norm_sigla(sigla)
    for l in buscar_linhas():
        if norm_sigla(l.get("sgl")) == alvo:
            return l
    return None


# ---------------------------------------------------------------------------
# Paradas
# ---------------------------------------------------------------------------

def paradas_da_linha(cod_linha):
    """Paradas ordenadas da linha (cod, end, sent) — sem coordenadas."""
    d = _jsonp(_get(f"/V3/buscarParadasPorLinha/{cod_linha}/0/{_praca()}/retornoJSON"),
               "retornoJSON")
    return d.get("paradas", [])


def paradas_proximas(lat, lon):
    """Paradas próximas a um ponto, COM coordenadas (x=lon, y=lat)."""
    d = _jsonp(_get(f"/buscarParadasProximas/{lon}/{lat}/1000/retornoJSON"), "retornoJSON")
    saida = []
    for p in d.get("paradas", []):
        try:
            saida.append({
                "cod": p.get("cod"),
                "nome": (p.get("desc") or "").strip(),
                "lat": float(p["y"]),
                "lon": float(p["x"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return saida


def itinerarios_da_linha(cod_linha, sigla, amostras=5):
    """codItinerários ativos: consulta previsões em paradas espalhadas pela linha."""
    try:
        paradas = paradas_da_linha(cod_linha)
    except Exception as e:
        log.warning(f"linha {sigla}: paradas falharam — {e}")
        return []
    if not paradas:
        return []
    n = len(paradas)
    idx = sorted({0, n // 4, n // 2, 3 * n // 4, n - 1})
    if amostras < len(idx):
        idx = idx[:amostras]
    codigos = set()
    for i in idx:
        cod = paradas[i].get("cod")
        if cod is None:
            continue
        try:
            d = _jsonp(_get(f"/V3/buscarPrevisoes/{cod}/false/0/{_praca()}/retornoJSON"),
                       "retornoJSON")
        except Exception:
            continue
        for p in d.get("previsoes", []):
            if norm_sigla(p.get("sgLin")) == norm_sigla(sigla) and p.get("codItinerario"):
                codigos.add(int(p["codItinerario"]))
        time.sleep(0.1)
    return sorted(codigos)


def veiculos_do_itinerario(cod_it):
    """Veículos ao vivo de um itinerário.

    Cada veículo tem: lat, long, direcao (rumo em graus), descricao (linha),
    numVeicGestor (id do veículo) e flagAnimacao.
    """
    d = _jsonp(_get(f"/V3/retornaVeiculosMapa/{cod_it}/0/{_praca()}/retornoJSONVeiculos"),
               "retornoJSONVeiculos")
    return d.get("veiculos", [])


def paradas_do_itinerario(cod_it, ttl=6 * 3600):
    """Paradas de um itinerário, COM coordenadas e na ordem da rota.

    Endpoint: buscarParadasPorItiComCoordenadas (sem prefixo V3 e sem praça).
    """
    agora = time.time()
    cache = _paradas_iti_cache.get(cod_it)
    if cache and (agora - cache[0]) < ttl:
        return cache[1]
    d = _jsonp(_get(f"/buscarParadasPorItiComCoordenadas/{cod_it}/0/retornoJSONPontosItinerario"),
               "retornoJSONPontosItinerario")
    saida = []
    for p in d.get("paradas", []):
        try:
            saida.append({
                "cod": p.get("cod"),
                "nome": (p.get("desc") or "").strip(),
                "lat": float(p["y"]),
                "lon": float(p["x"]),
                "cor": p.get("cor"),
            })
        except (KeyError, TypeError, ValueError):
            continue
    _paradas_iti_cache[cod_it] = (agora, saida)
    return saida


def previsoes_da_parada(cod_parada, acessiveis=False):
    """Previsões de uma parada (lista de {'prev','sgLin','cor','tpAcess',...})."""
    flag = "true" if acessiveis else "false"
    d = _jsonp(_get(f"/V3/buscarPrevisoes/{cod_parada}/{flag}/0/{_praca()}/retornoJSON"),
               "retornoJSON")
    return d.get("previsoes", [])


_paradas_iti_cache = {}


def rota_do_itinerario(cod_it, ttl=6 * 3600):
    """Traçado (Rota) de um itinerário — cacheado por 6 h."""
    agora = time.time()
    cache = _rota_cache.get(cod_it)
    if cache and (agora - cache[0]) < ttl:
        return cache[1]
    d = _jsonp(_get(f"/V3/buscarItinerario/{cod_it}/0/{_praca()}/retornoJSON"), "retornoJSON")
    pts = []
    for p in d.get("itinerarios", []):
        try:
            pts.append((float(p["coordY"]), float(p["coordX"])))
        except (KeyError, TypeError, ValueError):
            continue
    if len(pts) < 2:
        return None
    # import tardio para não criar ciclo
    from geo import Rota
    rota = Rota(pts)
    _rota_cache[cod_it] = (agora, rota)
    return rota
