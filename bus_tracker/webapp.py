"""Servidor web do App (painel do Home Assistant via ingress) + API JSON.

O painel roda DENTRO do ingress do HA, então todo caminho no HTML/JS precisa ser
relativo (o painel vive em /api/hassio_ingress/<token>/). Por isso o próprio
App também serve o Leaflet e as imagens do mapa (`/vendor/...` e
`/api/tile/...`), para o navegador não depender de CDN nem do servidor de tiles
— em rede com AdGuard/DNS filtrado, requisição externa do aparelho costuma
voltar como "Access blocked".
"""

import json
import logging
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import requests

import geo
import ha
import rotas
import siumobile as api

log = logging.getLogger("bus_tracker.web")

DIR_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
DIR_DADOS = os.environ.get("DIR_DADOS", "/data")
DIR_VENDOR = os.path.join(DIR_DADOS, "vendor")
DIR_TILES = os.path.join(DIR_DADOS, "tiles")

LEAFLET_VERSAO = "1.9.4"
UNPKG = f"https://unpkg.com/leaflet@{LEAFLET_VERSAO}/dist/"
VENDOR_PERMITIDO = {
    "leaflet.js", "leaflet.css",
    "images/layers.png", "images/layers-2x.png", "images/marker-icon.png",
    "images/marker-icon-2x.png", "images/marker-shadow.png",
}
UA_TILES = "BusTracker/3.0 (App Home Assistant; painel de onibus via SIUMobile)"
TILES_MAX = 8000
_tiles = {"n": 0, "falhas": 0}

TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".json": "application/json; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "bustracker/3.0"
    motor = None

    # ------------------------------------------------------------- utilidades
    def log_message(self, fmt, *args):
        log.debug("%s - %s", self.address_string(), fmt % args)

    def _json(self, dados, codigo=200):
        corpo = json.dumps(dados, ensure_ascii=False, default=str).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _erro(self, msg, codigo=400):
        self._json({"ok": False, "erro": msg}, codigo)

    def _corpo(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if not n:
            return {}
        bruto = self.rfile.read(n)
        try:
            return json.loads(bruto or b"{}")
        except Exception:
            return {}

    def _usuario(self):
        return self.headers.get("X-Remote-User-Display-Name") or self.headers.get("X-Remote-User-Name") or ""

    def _arquivo(self, caminho):
        alvo = os.path.normpath(os.path.join(DIR_WEB, caminho.lstrip("/")))
        if not alvo.startswith(DIR_WEB) or not os.path.isfile(alvo):
            return self._erro("não encontrado", 404)
        with open(alvo, "rb") as f:
            dados = f.read()
        ext = os.path.splitext(alvo)[1].lower()
        self.send_response(200)
        self.send_header("Content-Type", TIPOS.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(dados)

    # ------------------------------------------------- arquivos emprestados
    def _binario(self, caminho, tipo=None, cache=0):
        try:
            with open(caminho, "rb") as f:
                dados = f.read()
        except Exception as e:
            return self._erro(f"não li {caminho}: {e}", 500)
        self.send_response(200)
        self.send_header("Content-Type", tipo or TIPOS.get(os.path.splitext(caminho)[1].lower(),
                                                           "application/octet-stream"))
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", f"public, max-age={cache}" if cache else "no-store")
        self.end_headers()
        self.wfile.write(dados)

    def _baixar(self, url, destino, cabecalhos=None):
        """Baixa para o cache local (uma vez) e devolve o caminho."""
        if os.path.isfile(destino) and os.path.getsize(destino) > 0:
            return destino
        r = requests.get(url, headers=cabecalhos or {}, timeout=20)
        if r.status_code != 200 or not r.content:
            raise RuntimeError(f"HTTP {r.status_code} em {url}")
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "wb") as f:
            f.write(r.content)
        return destino

    def _vendor(self, nome):
        """Serve o Leaflet do próprio App (embutido no pacote ou baixado 1x)."""
        nome = nome.strip("/")
        if nome not in VENDOR_PERMITIDO:
            return self._erro("arquivo não permitido", 404)
        embutido = os.path.join(DIR_WEB, "vendor", nome)
        if os.path.isfile(embutido):
            return self._binario(embutido, cache=604800)
        try:
            caminho = self._baixar(UNPKG + nome, os.path.join(DIR_VENDOR, nome))
        except Exception as e:
            log.warning(f"vendor {nome}: {e}")
            return self._erro(f"não consegui obter {nome}", 502)
        return self._binario(caminho, cache=604800)

    def _tile(self, caminho):
        """Repassa as imagens do mapa pelo App (o aparelho não fala com o OSM)."""
        partes = caminho.strip("/").split("/")
        if len(partes) != 5:
            return self._erro("tile inválido", 404)
        _, _, z, x, y = partes
        if not (z.isdigit() and x.isdigit() and y.replace(".png", "").isdigit()):
            return self._erro("coordenadas inválidas", 400)
        y = y.replace(".png", "")
        destino = os.path.join(DIR_TILES, z, x, f"{y}.png")
        if not os.path.isfile(destino):
            try:
                self._baixar(f"https://tile.openstreetmap.org/{z}/{x}/{y}.png", destino,
                             {"User-Agent": UA_TILES, "Referer": "https://via-feira-tracker.local/"})
                _tiles["n"] += 1
                if _tiles["n"] % 300 == 0:
                    self._limpar_tiles()
            except Exception as e:
                _tiles["falhas"] += 1
                if _tiles["falhas"] == 1 or _tiles["falhas"] % 50 == 0:
                    log.warning(f"tile {z}/{x}/{y}: {e} (falhas: {_tiles['falhas']})")
                    self.motor.registrar(f"mapa: falha ao baixar imagem do OSM ({e})", "warning")
                # devolve um quadrado vazio para o mapa não travar
                return self._erro("tile indisponível", 502)
        return self._binario(destino, "image/png", cache=604800)

    def _limpar_tiles(self):
        try:
            arqs = []
            for raiz, _, nomes in os.walk(DIR_TILES):
                for n in nomes:
                    p = os.path.join(raiz, n)
                    arqs.append((os.path.getmtime(p), p))
            if len(arqs) > TILES_MAX:
                arqs.sort()
                for _, p in arqs[:len(arqs) - TILES_MAX]:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        except Exception as e:
            log.debug(f"limpeza de tiles: {e}")

    # ------------------------------------------------------------------ rotas
    def do_GET(self):
        caminho = self.path.split("?")[0]
        motor = self.motor
        if caminho in ("/", "/index.html"):
            return self._arquivo("index.html")
        if caminho.startswith("/static/"):
            return self._arquivo(caminho.replace("/static/", "", 1))
        if caminho.startswith("/vendor/"):
            return self._vendor(caminho[len("/vendor/"):])
        if caminho.startswith("/api/tile/"):
            return self._tile(caminho)
        if caminho == "/api/estado":
            return self._json(self._estado())
        if caminho == "/api/mapa":
            return self._json(motor.estado_publico())
        if caminho.startswith("/api/onibus/"):
            return self._json(motor.detalhes_onibus(caminho.rsplit("/", 1)[-1]))
        if caminho == "/api/paradas":
            q = parse_qs(urlparse(self.path).query)
            siglas = [s.strip() for s in (q.get("linha") or []) if s.strip()]
            if not siglas and q.get("linhas"):
                siglas = [s.strip() for s in q["linhas"][0].split(",") if s.strip()]
            paradas, vistos = [], set()
            for sigla in siglas:
                linha = api.linha_por_sigla(sigla)
                if not linha:
                    continue
                try:
                    for p in api.paradas_com_coordenadas(linha["cod"]):
                        chave = (p.get("cod"), round(p.get("lat", 0), 5), round(p.get("lon", 0), 5))
                        if chave in vistos:
                            continue
                        vistos.add(chave)
                        paradas.append(p)
                except Exception as e:
                    log.debug(f"paradas {sigla}: {e}")
            return self._json({"ok": True, "paradas": paradas})
        if caminho == "/api/paradas_proximas":
            q = parse_qs(urlparse(self.path).query)
            try:
                lat = float((q.get("lat") or [""])[0])
                lon = float((q.get("lon") or [""])[0])
            except (TypeError, ValueError):
                return self._erro("informe lat/lon")
            try:
                raio = int((q.get("raio") or [motor.cfg["ajustes"].get("raio_destino_m", 3000)])[0])
            except (TypeError, ValueError):
                raio = 3000
            raio = max(100, min(raio, 20000))
            centro = (lat, lon)
            paradas, vistos = [], set()

            def _add(p):
                if p.get("lat") is None or p.get("lon") is None:
                    return
                chave = (p.get("cod"), round(p["lat"], 5), round(p["lon"], 5))
                if chave in vistos:
                    return
                vistos.add(chave)
                paradas.append({"cod": p.get("cod"), "nome": p.get("nome"),
                                "lat": p["lat"], "lon": p["lon"],
                                "dist": round(geo.haversine(centro, (p["lat"], p["lon"])))})

            # 1) paradas próximas do ponto tocado (a API ignora o raio pedido,
            #    então serve só como ponto de partida)
            try:
                for p in api.paradas_proximas(lat, lon, raio):
                    _add(p)
            except Exception as e:
                log.debug(f"paradas próximas: {e}")
            # 2) completa com as paradas das linhas monitoradas dentro do raio
            try:
                siglas = motor.linhas_observadas()[:40]
            except Exception:
                siglas = []
            for sigla in siglas:
                try:
                    linha = api.linha_por_sigla(sigla)
                    if not linha:
                        continue
                    for p in api.paradas_com_coordenadas(linha["cod"]):
                        if geo.haversine(centro, (p["lat"], p["lon"])) <= raio:
                            _add(p)
                except Exception:
                    continue
            paradas.sort(key=lambda x: x["dist"])
            return self._json({"ok": True, "raio": raio, "paradas": paradas})
        if caminho == "/api/log":
            return self._json({"log": list(motor.log)})
        if caminho == "/api/painel":
            try:
                html = open(os.path.join(DIR_WEB, "index.html"), encoding="utf-8").read()
            except Exception as e:
                return self._erro(f"index.html: {e}", 500)
            return self._json({"ok": True, "html_len": len(html)})
        return self._erro("rota desconhecida", 404)

    def do_POST(self):
        caminho = self.path.split("?")[0]
        motor = self.motor
        corpo = self._corpo()
        cfg = motor.cfg

        if caminho == "/api/ajustes":
            for chave, valor in (corpo or {}).items():
                if chave in cfg["ajustes"]:
                    padrao = cfg["ajustes"][chave]
                    if isinstance(padrao, bool):
                        valor = bool(valor)
                    elif isinstance(padrao, (int, float)) and not isinstance(padrao, bool):
                        try:
                            valor = int(valor) if isinstance(padrao, int) else float(valor)
                        except (TypeError, ValueError):
                            continue
                    cfg["ajustes"][chave] = valor
            motor.salvar(cfg)
            motor.registrar("Ajustes atualizados")
            return self._json({"ok": True, "ajustes": cfg["ajustes"]})

        if caminho == "/api/cidade":
            cidade = str(corpo.get("cidade") or "").strip()
            base = str(corpo.get("api_base") or "").strip()
            praca = str(corpo.get("api_praca") or "").strip()
            pacote = str(corpo.get("app_package") or "").strip()
            if not cidade and not base:
                return self._erro("informe a cidade")
            api.configurar(cidade=cidade or None, base=base or None,
                           praca=praca or None, pacote=pacote or None)
            atual = api.cidade_atual()
            cfg["cidade"] = atual
            motor.salvar(cfg)
            motor.reiniciar()
            motor.registrar(f"Cidade alterada para {atual['nome']}")
            return self._json({"ok": True, "cidade": atual})

        if caminho == "/api/mapa":
            mapa = cfg.setdefault("mapa", {})
            for chave in ("onibus", "pessoas"):
                if chave in corpo:
                    mapa[chave] = sorted({str(x) for x in (corpo[chave] or [])})
            for chave in ("rotas", "pontos"):
                if chave in corpo:
                    mapa[chave] = bool(corpo[chave])
            motor.salvar(cfg)
            return self._json({"ok": True, "mapa": mapa})

        if caminho == "/api/regras":
            regra = corpo.get("regra") or corpo
            regra = self._limpa_regra(regra)
            if not regra.get("linha"):
                return self._erro("informe a linha")
            if not regra.get("pessoas"):
                return self._erro("selecione ao menos uma pessoa")
            lista = cfg.setdefault("regras", [])
            for i, r in enumerate(lista):
                if r.get("id") == regra["id"]:
                    lista[i] = regra
                    break
            else:
                lista.append(regra)
            motor.salvar(cfg)
            motor.registrar(f"Aviso salvo: linha {regra['linha']} · {len(regra['pessoas'])} pessoa(s)")
            return self._json({"ok": True, "regra": regra})

        if caminho.startswith("/api/regras/"):
            rid = caminho.rsplit("/", 1)[-1]
            cfg["regras"] = [r for r in cfg.get("regras", []) if r.get("id") != rid]
            motor.salvar(cfg)
            motor.registrar("Aviso removido")
            return self._json({"ok": True})

        if caminho == "/api/pessoas":
            pessoa = corpo.get("pessoa") or corpo
            pessoa = self._limpa_pessoa(pessoa)
            if not pessoa.get("nome"):
                return self._erro("informe o nome")
            if not pessoa.get("notify"):
                return self._erro("escolha o celular que recebe as notificações")
            lista = cfg.setdefault("pessoas", [])
            for i, p in enumerate(lista):
                if p.get("id") == pessoa["id"]:
                    lista[i] = pessoa
                    break
            else:
                lista.append(pessoa)
            motor.salvar(cfg)
            motor.registrar(f"Pessoa salva: {pessoa['nome']}")
            return self._json({"ok": True, "pessoa": pessoa})

        if caminho.startswith("/api/pessoas/"):
            pid = caminho.rsplit("/", 1)[-1]
            cfg["pessoas"] = [p for p in cfg.get("pessoas", []) if p.get("id") != pid]
            for r in cfg.get("regras", []):
                r["pessoas"] = [x for x in r.get("pessoas", []) if x != pid]
            cfg.setdefault("mapa", {}).setdefault("pessoas", [])
            cfg["mapa"]["pessoas"] = [x for x in cfg["mapa"]["pessoas"] if x != pid]
            motor.salvar(cfg)
            return self._json({"ok": True})

        if caminho == "/api/casa":
            casa = cfg.setdefault("casa", {})
            if "entidade" in corpo:
                casa["entidade"] = str(corpo.get("entidade") or "").strip()
            if "raio" in corpo:
                try:
                    casa["raio"] = max(30, int(corpo["raio"]))
                except (TypeError, ValueError):
                    pass
            if "lat" in corpo and "lon" in corpo:
                try:
                    casa["lat"] = float(corpo["lat"])
                    casa["lon"] = float(corpo["lon"])
                except (TypeError, ValueError):
                    casa["lat"] = casa["lon"] = None
            if "osrm_base" in corpo:
                cfg["ajustes"]["osrm_base"] = str(corpo.get("osrm_base") or "").strip()
                rotas.configurar(cfg["ajustes"]["osrm_base"])
            motor.salvar(cfg)
            motor.registrar("Casa/zonas atualizadas")
            return self._json({"ok": True, "casa": casa})

        if caminho == "/api/trajetos":
            trajeto = self._limpa_trajeto(corpo.get("trajeto") or corpo)
            if not trajeto.get("pessoa"):
                return self._erro("informe a pessoa")
            lista = cfg.setdefault("trajetos", [])
            for i, x in enumerate(lista):
                if x.get("id") == trajeto["id"]:
                    lista[i] = trajeto
                    break
            else:
                lista.append(trajeto)
            motor.salvar(cfg)
            linhas_txt = ", ".join(trajeto["linhas"]) or "todas do destino"
            motor.registrar(f"Trajeto salvo: {linhas_txt} · "
                            f"{len(trajeto['horarios'])} horário(s)")
            return self._json({"ok": True, "trajeto": trajeto})

        if caminho.startswith("/api/trajetos/"):
            tid = caminho.rsplit("/", 1)[-1]
            cfg["trajetos"] = [x for x in cfg.get("trajetos", []) if x.get("id") != tid]
            motor.salvar(cfg)
            motor.registrar("Trajeto removido")
            return self._json({"ok": True})

        if caminho == "/api/trajeto_teste":
            pessoa = motor._pessoa(str(corpo.get("pessoa") or ""))
            trajeto = next((x for x in cfg.get("trajetos", []) if x.get("id") == corpo.get("id")), None)
            if not pessoa or not trajeto:
                return self._erro("pessoa ou trajeto não encontrado", 404)
            info = motor.calcular_trajeto(trajeto)
            if not info:
                return self._erro("não achei ônibus perto de " + pessoa["nome"], 404)
            bus = info["onibus"][0] if info["onibus"] else {"id": "0", "eta_min": None,
                                                            "risco": "sem-previsao"}
            motor.enviar_saida(info, bus)
            return self._json({"ok": True, "info": info})

        if caminho == "/api/trajeto_candidatos":
            trajeto = self._limpa_trajeto(corpo.get("trajeto") or corpo)
            if not trajeto.get("pessoa"):
                return self._erro("informe a pessoa")
            if not trajeto.get("destino", {}).get("lat"):
                return self._erro("escolha o destino")
            return self._json({"ok": True, "pontos": motor.candidatos_embarque(trajeto)})

        if caminho == "/api/ha/pessoas":
            pessoas, rastreadores, notificacoes = motor.pessoas_ha()
            return self._json({"pessoas": pessoas, "rastreadores": rastreadores, "notificacoes": notificacoes})

        if caminho == "/api/atualizar":
            threading.Thread(target=motor.ciclo, daemon=True).start()
            return self._json({"ok": True})

        if caminho.startswith("/api/parar/"):
            chave = caminho.rsplit("/", 1)[-1]
            return self._json({"ok": motor.parar_rastreio(chave)})

        if caminho.startswith("/api/teste/"):
            pid = caminho.rsplit("/", 1)[-1]
            pessoas = {p["id"]: p for p in cfg.get("pessoas", [])}
            pessoa = pessoas.get(pid)
            if not pessoa:
                return self._erro("pessoa não encontrada", 404)
            motor._notificar(
                pessoa,
                "🚌 Teste do Bus Tracker",
                "Se você está vendo isso, os avisos estão funcionando.",
                {"tag": "bustracker_teste",
                 "actions": [
                     {"action": f"RECUSAR|{pid}|085|0", "title": "Ok"},
                 ]},
            )
            motor.registrar(f"Notificação de teste enviada a {pessoa['nome']}")
            return self._json({"ok": True})

        if caminho == "/api/agora":
            """Dispara um aviso imediato (ignora horário e cooldown) — usado no botão Testar."""
            pid = corpo.get("pessoa")
            sigla = corpo.get("linha")
            pessoas = {p["id"]: p for p in cfg.get("pessoas", [])}
            pessoa = pessoas.get(pid)
            if not pessoa or not sigla:
                return self._erro("informe pessoa e linha")
            alvo = motor.alvo(pessoa, sigla, forcar=True)
            if not alvo or alvo.get("passa_a_m") is None:
                return self._erro("essa linha não passa perto de " + pessoa["nome"], 404)
            lista = motor.candidatos(sigla, alvo, 10 ** 7)
            if not lista:
                return self._erro("nenhum ônibus dessa linha no mapa agora", 404)
            bus = lista[0]
            motor.enviar_aviso({"id": "teste", "linha": sigla}, pessoa, bus, alvo)
            return self._json({"ok": True, "veiculo": bus["id"], "dist_ponto": round(bus["dist_ponto"]),
                               "eta_min": bus["eta_min"],
                               "ponto": alvo.get("parada") or {"nome": f"onde o ônibus passa ({round(alvo.get('passa_a_m') or 0)} m de você)"}})

        return self._erro("rota desconhecida", 404)

    # ------------------------------------------------------------- sanitização
    def _limpa_regra(self, regra):
        dias = []
        for d in regra.get("dias") or []:
            try:
                d = int(d)
            except (TypeError, ValueError):
                continue
            if 0 <= d <= 6:
                dias.append(d)
        return {
            "id": str(regra.get("id") or uuid.uuid4().hex[:8]),
            "ativo": bool(regra.get("ativo", True)),
            "linha": str(regra.get("linha") or "").strip(),
            "pessoas": [str(p) for p in (regra.get("pessoas") or [])],
            "dias": sorted(set(dias)) if dias else list(range(7)),
            "inicio": self._hora(regra.get("inicio"), "00:00"),
            "fim": self._hora(regra.get("fim"), "23:59"),
        }

    def _limpa_pessoa(self, pessoa):
        return {
            "id": str(pessoa.get("id") or uuid.uuid4().hex[:8]),
            "nome": str(pessoa.get("nome") or "").strip(),
            "ativo": bool(pessoa.get("ativo", True)),
            "notify": str(pessoa.get("notify") or "").strip(),
            "entidade": str(pessoa.get("entidade") or "").strip(),
            "atividade": str(pessoa.get("atividade") or "").strip(),
        }

    def _limpa_trajeto(self, t):
        horarios = []
        for h in (t.get("horarios") or []):
            h = str(h).strip()
            if re.match(r"^\d{1,2}:\d{2}$", h):
                hh, mm = h.split(":")
                horarios.append(f"{int(hh):02d}:{int(mm):02d}")
        dias = []
        for d in (t.get("dias") or []):
            try:
                d = int(d)
            except (TypeError, ValueError):
                continue
            if 0 <= d <= 6:
                dias.append(d)
        linhas = []
        for s in (t.get("linhas") or ([t.get("linha")] if t.get("linha") else [])):
            s = str(s or "").strip()
            if s and s not in linhas:
                linhas.append(s)
        destino = t.get("destino") or {}
        if not isinstance(destino, dict):
            destino = {"nome": str(destino)}
        lat, lon = destino.get("lat"), destino.get("lon")
        try:
            lat = float(lat) if lat not in (None, "") else None
            lon = float(lon) if lon not in (None, "") else None
        except (TypeError, ValueError):
            lat = lon = None
        tipo = str(t.get("tipo_horario") or "ponto").strip().lower()
        if tipo not in ("ponto", "liberado", "chegar"):
            tipo = "ponto"
        return {
            "id": str(t.get("id") or uuid.uuid4().hex[:8]),
            "ativo": bool(t.get("ativo", True)),
            "pessoa": str(t.get("pessoa") or "").strip(),
            "linhas": linhas,
            "tipo_horario": tipo,
            "destino": {"cod": str(destino.get("cod") or "").strip(),
                        "nome": str(destino.get("nome") or "").strip(),
                        "lat": lat, "lon": lon},
            "ponto": self._ponto_embarque(t.get("ponto")),
            "dias": sorted(set(dias)) if dias else list(range(7)),
            "horarios": sorted(set(horarios)),
        }

    def _ponto_embarque(self, p):
        """Ponto de embarque escolhido à mão (ou vazio = automático)."""
        if not isinstance(p, dict):
            return {"nome": "", "cod": "", "lat": None, "lon": None}
        try:
            plat = float(p.get("lat")) if p.get("lat") not in (None, "") else None
            plon = float(p.get("lon")) if p.get("lon") not in (None, "") else None
        except (TypeError, ValueError):
            plat = plon = None
        return {"nome": str(p.get("nome") or "").strip(),
                "cod": str(p.get("cod") or "").strip(),
                "lat": plat, "lon": plon}

    def _hora(self, valor, padrao):
        if isinstance(valor, str) and re.match(r"^\d{1,2}:\d{2}$", valor.strip()):
            h, m = valor.strip().split(":")
            return f"{int(h):02d}:{int(m):02d}"
        return padrao

    # ------------------------------------------------------------------ estado
    def _estado(self):
        motor = self.motor
        cfg = motor.cfg
        linhas = []
        try:
            for l in api.buscar_linhas():
                linhas.append({"sigla": l.get("sgl"), "nome": l.get("nom"), "cod": l.get("cod")})
        except Exception as e:
            motor.registrar(f"não consegui listar as linhas: {e}", "warning")
        pessoas_ha, rastreadores, notificacoes = motor.pessoas_ha()
        return {
            "ok": True,
            "ajustes": cfg["ajustes"],
            "pessoas": cfg.get("pessoas", []),
            "regras": cfg.get("regras", []),
            "trajetos": cfg.get("trajetos", []),
            "casa": cfg.get("casa", {}),
            "mapa": cfg.get("mapa", {}),
            "cidade": api.cidade_atual(),
            "cidades": api.cidades(),
            "linhas": linhas,
            "linhas_observadas": motor.linhas_observadas(),
            "ha": {"pessoas": pessoas_ha, "rastreadores": rastreadores, "notificacoes": notificacoes},
            "status": {
                "ultimo_ciclo": motor.ultimo_ciclo,
                "erro": motor.erro_ciclo,
                "onibus": len(motor.onibus),
                "rastreios": len(motor.rastreios),
                "escutador": getattr(self.server, "escutador_conectado", lambda: False)(),
                "usuario": self._usuario(),
                "agora": time.time(),
            },
        }


def criar(motor, porta, escutador=None):
    Handler.motor = motor
    httpd = ThreadingHTTPServer(("0.0.0.0", porta), Handler)
    httpd.daemon_threads = True
    httpd.escutador_conectado = (lambda: bool(escutador and escutador.conectado)) if escutador else (lambda: False)
    return httpd
