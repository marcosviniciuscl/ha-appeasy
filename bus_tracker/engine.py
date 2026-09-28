"""Motor: observa os ônibus, decide os avisos e conduz o rastreio ao vivo."""

import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import geo
import ha
import rotas as rotas_ruas
import siumobile as api
from siumobile import norm_sigla

log = logging.getLogger("bus_tracker.motor")

DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
RASTREIO_MAX_MIN = 45
CHEGADA_M = 200


def _tz(nome):
    try:
        return ZoneInfo(nome)
    except Exception:
        return ZoneInfo("UTC")


def _fmt_dist(m):
    if m is None:
        return "?"
    return f"{m/1000:.1f} km" if m >= 1000 else f"{int(round(m))} m"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _hhmm(valor):
    """'06:30' -> minutos desde a meia-noite, ou None."""
    try:
        h, m = str(valor).strip().split(":")
        return int(h) * 60 + int(m)
    except (TypeError, ValueError):
        return None


class Motor:
    def __init__(self, cfg, salvar_cb, linhas_extras=None):
        self.cfg = cfg
        self.salvar = salvar_cb
        self.linhas_extras = linhas_extras or []
        self.lock = threading.RLock()
        self.onibus = {}          # id -> dados do veículo
        self.rastreios = {}       # pessoa_id -> estado do rastreio
        self.avisos = {}          # (regra_id, pessoa_id, bus_id) -> ts
        self.alvos = {}           # (pessoa_id, sigla) -> {'parada','ts','pos'}
        self.log = deque(maxlen=300)
        self.itinerarios = {}     # sigla -> {'its': [(cod_it, ts)], 'pessoas': {...}}
        self.ultimo_ciclo = 0.0
        self.erro_ciclo = ""
        self.pausado = False
        self._cache_destino = {}  # (lat,lon) -> (ts, [siglas]) linhas que atendem o destino
        self._trajeto_log = {}    # trajeto_id -> assinatura do último log (evita repetir)

    # ------------------------------------------------------------------ log
    def registrar(self, msg, nivel="info"):
        with self.lock:
            self.log.appendleft({
                "ts": time.time(),
                "hora": datetime.now(_tz(self.cfg["ajustes"]["fuso"])).strftime("%H:%M:%S"),
                "nivel": nivel,
                "msg": msg,
            })
        getattr(log, nivel if nivel in ("info", "warning", "error") else "info")(msg)

    def _diag(self, t, msg):
        """Log detalhado de um trajeto (só quando o modo diagnóstico está ligado)."""
        if self.cfg["ajustes"].get("diagnostico"):
            self.registrar(f"[diag trajeto {t.get('id')}] {msg}")

    def _log_trajeto(self, t, info):
        """Registra no atividade o que o trajeto escolheu (só quando muda)."""
        tid = str(t.get("id"))
        if not info:
            sig = "sem-candidatos"
            if self._trajeto_log.get(tid) != sig:
                self._trajeto_log[tid] = sig
                self.registrar(f"Trajeto {tid}: nenhum ônibus indo ao destino foi encontrado",
                               "warning")
            return
        b = (info.get("onibus") or [None])
        b = b[0] if b else None
        sig = (f"{info['ponto']['nome']}|{b.get('id') if b else '-'}|"
               f"{b.get('eta_min') if b else '-'}|{info['agora']}|{info.get('longe')}")
        if self._trajeto_log.get(tid) == sig:
            return
        self._trajeto_log[tid] = sig
        dest = (info.get("destino") or {}).get("nome") or "—"
        janela = "" if info.get("agora") else " (fora do horário)"
        longe = (" · LONGE: ponto a %d m (limite %d m)" %
                 (info["ponto"]["dist_m"], info.get("dist_max_m") or 0)) if info.get("longe") else ""
        if b:
            bus_txt = (f"próximo ônibus {b.get('id')} (linha {b.get('linha')}, "
                       f"ETA {b.get('eta_min')} min, {b.get('risco')})")
        else:
            bus_txt = "nenhum ônibus indo ao ponto agora"
        self.registrar(
            f"Trajeto {tid} · {info['pessoa']}: destino {dest} → ponto {info['ponto']['nome']} "
            f"({info['ponto']['dist_m']} m a pé) · {bus_txt}{janela}{longe}",
            "warning" if info.get("longe") else "info")

    # ---------------------------------------------------------------- ciclo
    def ciclo(self):
        """Um ciclo de leitura da API: atualiza a posição de todos os ônibus."""
        if self.pausado:
            return
        siglas = self.linhas_observadas()
        if not siglas:
            self.ultimo_ciclo = time.time()
            return
        try:
            catalogo = {norm_sigla(l.get("sgl")): l for l in api.buscar_linhas()}
        except Exception as e:
            self.erro_ciclo = f"API de linhas fora do ar: {e}"
            self.registrar(self.erro_ciclo, "warning")
            return

        vistos = {}
        novos = 0
        for sigla in siglas:
            linha = catalogo.get(sigla)
            if not linha:
                continue
            sigla_exib = str(linha.get("sgl") or sigla)
            try:
                itinerarios = self._itinerarios(sigla, linha)
            except Exception as e:
                self.registrar(f"linha {sigla_exib}: falha ao buscar itinerários ({e})", "warning")
                continue
            if not itinerarios:
                continue
            for cod_it in itinerarios:
                rota = None
                try:
                    rota = api.rota_do_itinerario(cod_it)
                except Exception as e:
                    log.debug(f"rota {cod_it}: {e}")
                try:
                    veiculos = api.veiculos_do_itinerario(cod_it)
                except Exception as e:
                    self.registrar(f"itinerário {cod_it}: veículos falharam ({e})", "warning")
                    continue
                for v in veiculos:
                    vid = v.get("numVeicGestor")
                    if not vid:
                        continue
                    try:
                        lat = float(v["lat"])
                        lon = float(v["long"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    vistos[str(vid)] = (sigla_exib, cod_it, rota, lat, lon, v)
                time.sleep(0.2)

        agora = time.time()
        with self.lock:
            for vid, (sigla, cod_it, rota, lat, lon, bruto) in vistos.items():
                antigo = self.onibus.get(vid)
                novo = {
                    "id": vid,
                    "linha": sigla,
                    "cod_it": cod_it,
                    "lat": lat,
                    "lon": lon,
                    "ts": agora,
                    "em_movimento": str(bruto.get("flagAnimacao", "")).lower() == "true",
                    "historico": [],
                    "vel_kmh": 0.0,
                    "s": None,
                    "offset": None,
                    "rumo": None,
                    "cor": bruto.get("cor"),
                    "direcao": _num(bruto.get("direcao")),
                    "descricao": bruto.get("descricao"),
                    "primeira_vez": antigo is None,
                }
                if antigo:
                    novo["historico"] = antigo.get("historico", [])[-6:]
                    novo["vel_kmh"] = antigo.get("vel_kmh", 0.0)
                    novo["s"] = antigo.get("s")
                    if novo.get("cor") is None:
                        novo["cor"] = antigo.get("cor")
                    if novo.get("direcao") is None:
                        novo["direcao"] = antigo.get("direcao")
                    if not novo.get("descricao"):
                        novo["descricao"] = antigo.get("descricao")
                    if rota and antigo.get("cod_it") != cod_it:
                        novo["s"] = None  # trocou de itinerário: reprojeta
                    novo["historico"].append((agora, lat, lon))
                    dt = agora - antigo["ts"]
                    d = geo.haversine((lat, lon), (antigo["lat"], antigo["lon"]))
                    if 5 < dt < 240 and d > 15:
                        v_kmh = (d / dt) * 3.6
                        novo["vel_kmh"] = round(0.6 * antigo.get("vel_kmh", v_kmh) + 0.4 * v_kmh, 1)
                        novo["rumo"] = geo.bearing((antigo["lat"], antigo["lon"]), (lat, lon))
                    elif antigo.get("rumo") is not None:
                        novo["rumo"] = antigo["rumo"]
                if rota:
                    s, offset = rota.projetar((lat, lon))
                    novo["s"] = s
                    novo["offset"] = offset
                    novo["comprimento_rota"] = rota.comprimento
                else:
                    novo["comprimento_rota"] = antigo.get("comprimento_rota") if antigo else None
                self.onibus[vid] = novo
                if novo["primeira_vez"]:
                    novos += 1

            sumidos = [vid for vid in list(self.onibus) if vid not in vistos]
            for vid in sumidos:
                del self.onibus[vid]
                for chave in [k for k in self.avisos if k[2] == vid]:
                    self.avisos.pop(chave, None)

        for vid in sumidos:
            ha.remover_estado(f"device_tracker.bustracker_{vid}")
        self.ultimo_ciclo = time.time()
        self.erro_ciclo = ""
        if novos or sumidos:
            self.registrar(f"{len(vistos)} ônibus no mapa ({novos} novo(s), {len(sumidos)} saiu/saíram)")

    def linhas_observadas(self):
        siglas = set()
        for regra in self.cfg.get("regras", []):
            if regra.get("ativo"):
                siglas.add(norm_sigla(regra.get("linha")))
        for sigla in self.cfg.get("mapa", {}).get("onibus", []):
            siglas.add(norm_sigla(sigla))
        for sigla in self.linhas_extras:
            siglas.add(norm_sigla(sigla))
        vazios = [t for t in self.cfg.get("trajetos", [])
                  if t.get("ativo", True) and not self._siglas_trajeto(t)]
        for t in self.cfg.get("trajetos", []):
            if not t.get("ativo", True):
                continue
            for sigla in self._siglas_trajeto(t):
                siglas.add(norm_sigla(sigla))
        siglas.discard("")
        # sem linha no trajeto: em "cidade" sempre descobre; em "monitoradas"
        # descobre apenas quando não há nenhuma linha monitorada no app
        modo_cidade = str(self.cfg["ajustes"].get("trajetos_sem_linha", "monitoradas")) == "cidade"
        if modo_cidade or not siglas:
            for t in vazios:
                for sigla in self._linhas_do_destino(t.get("destino") or {}):
                    siglas.add(norm_sigla(sigla))
        siglas.discard("")
        return sorted(siglas)

    def _siglas_trajeto(self, t):
        """Siglas declaradas no trajeto (novo campo `linhas` ou antigo `linha`)."""
        linhas = [str(s).strip() for s in (t.get("linhas") or []) if str(s).strip()]
        if not linhas and t.get("linha"):
            linhas = [str(t["linha"]).strip()]
        return linhas

    def _linhas_do_destino(self, destino, ttl=1800):
        """Linhas que atendem o destino, descobertas pelas paradas próximas.

        Usa as previsões ativas das paradas num raio de 1 km do destino, então é
        uma aproximação do que está circulando por lá (cache de 30 min).
        """
        try:
            lat, lon = float(destino.get("lat")), float(destino.get("lon"))
        except (TypeError, ValueError):
            return []
        chave = (round(lat, 4), round(lon, 4))
        cache = self._cache_destino.get(chave)
        if cache and (time.time() - cache[0]) < ttl:
            return cache[1]
        siglas = set()
        try:
            paradas = api.paradas_proximas(lat, lon)
        except Exception as e:
            log.debug(f"paradas próximas do destino: {e}")
            paradas = []
        for p in paradas[:6]:
            try:
                for pv in api.previsoes_da_parada(p["cod"]):
                    s = pv.get("sgLin")
                    if s:
                        siglas.add(norm_sigla(s))
            except Exception:
                continue
        resultado = sorted(siglas)
        self._cache_destino[chave] = (time.time(), resultado)
        return resultado

    def linhas_do_trajeto(self, t):
        """Linhas que o trajeto considera.

        Com `linhas` preenchido, usa as escolhidas. Sem linha, respeita o ajuste
        `trajetos_sem_linha`: "monitoradas" (padrão) usa as linhas já monitoradas
        no app; "cidade" descobre linhas que atendem o destino.
        """
        linhas = self._siglas_trajeto(t)
        if linhas:
            return linhas
        destino = t.get("destino") or {}
        modo = str(self.cfg["ajustes"].get("trajetos_sem_linha", "monitoradas"))
        if modo == "cidade":
            return self._linhas_do_destino(destino)
        observadas = self.linhas_observadas()
        # sem nenhuma linha monitorada, ainda tenta descobrir pelo destino
        if not observadas:
            return self._linhas_do_destino(destino)
        return self._filtrar_por_destino(observadas, destino)

    def _filtrar_por_destino(self, linhas, destino, tol_m=800):
        """Mantém só as linhas que passam perto do destino (as monitoradas)."""
        try:
            lat, lon = float(destino.get("lat")), float(destino.get("lon"))
        except (TypeError, ValueError):
            return linhas
        ponto = (lat, lon)
        filtradas = []
        for sigla in linhas:
            melhor = None
            for rota in self._rotas_da_linha(sigla):
                _, off = rota.projetar(ponto)
                if melhor is None or off < melhor:
                    melhor = off
            if melhor is not None and melhor <= tol_m:
                filtradas.append(sigla)
        # se nenhuma passou (ou ainda sem traçado), não bloqueia o trajeto
        return filtradas or linhas

    def _itinerarios(self, sigla, linha):
        """codItinerários ativos da linha, com cache de 10 min."""
        agora = time.time()
        dados = self.itinerarios.get(sigla)
        if dados and (agora - dados["ts"]) < 600 and dados["its"]:
            return [c for c, _ in dados["its"]]
        its = api.itinerarios_da_linha(linha["cod"], sigla)
        if its:
            self.itinerarios[sigla] = {"ts": agora, "its": [(c, agora) for c in its]}
        elif dados:
            # mantém por mais um tempo: previsões podem falhar sem que a linha pare
            if (agora - dados["ts"]) < 1800:
                return [c for c, _ in dados["its"]]
        return its

    def reiniciar(self):
        """Limpa o estado ao trocar de cidade/linhas e dispara uma nova leitura."""
        with self.lock:
            antigos = list(self.onibus)
            self.onibus.clear()
            self.avisos.clear()
            self.alvos.clear()
            self.itinerarios.clear()
            self.ultimo_ciclo = 0.0
            self.erro_ciclo = ""
        for vid in antigos:
            try:
                ha.remover_estado(f"device_tracker.bustracker_{vid}")
            except Exception:
                pass
        threading.Thread(target=self.ciclo, daemon=True, name="ciclo-reinicio").start()

    def detalhes_onibus(self, bus_id):
        """Detalhes de um veículo: traçado, paradas do itinerário e ETA até elas."""
        with self.lock:
            b = dict(self.onibus.get(str(bus_id)) or {})
        if not b:
            return {"ok": False, "erro": "veículo fora do mapa"}
        cod_it = b.get("cod_it")
        rota = None
        try:
            rota = api.rota_do_itinerario(cod_it) if cod_it else None
        except Exception as e:
            log.debug(f"rota {cod_it}: {e}")

        pontos = []
        if rota:
            passo = max(1, len(rota.pts) // 700)
            pontos = [[round(p[0], 5), round(p[1], 5)] for p in rota.pts[::passo]]

        vel = max(b.get("vel_kmh") or 0.0,
                  float(self.cfg["ajustes"].get("velocidade_min_kmh", 12)))
        s_bus = b.get("s")
        paradas = []
        try:
            for p in api.paradas_do_itinerario(cod_it):
                d = None
                if rota and s_bus is not None:
                    s_p, _ = rota.projetar((p["lat"], p["lon"]))
                    d = s_p - s_bus
                paradas.append({
                    "cod": p.get("cod"), "nome": p["nome"], "lat": p["lat"], "lon": p["lon"],
                    "cor": p.get("cor"),
                    "dist_m": round(max(d, 0)) if d is not None else None,
                    "eta_min": round((max(d, 0) / 1000) / vel * 60, 1) if d is not None else None,
                    "passou": bool(d is not None and d < -40),
                })
        except Exception as e:
            log.debug(f"paradas do itinerário {cod_it}: {e}")

        # Previsão "oficial" (como o app: "6 Minutos" / "SAÍDA: HH:MM") por parada
        previsao = acessivel = sentido = None
        for p in [x for x in paradas if not x["passou"]][:4]:
            if not p.get("cod"):
                continue
            try:
                for pv in api.previsoes_da_parada(p["cod"]):
                    if str(pv.get("numVeicGestor")) == str(bus_id):
                        p["prev"] = pv.get("prev")
                        p["acessivel"] = pv.get("tpAcess") == 1
                        if not sentido:
                            sentido = pv.get("apelidoLinha")
                        if previsao is None:
                            previsao = pv.get("prev")
                            acessivel = pv.get("tpAcess") == 1
                        break
            except Exception as e:
                log.debug(f"previsão da parada {p.get('cod')}: {e}")

        return {
            "ok": True,
            "onibus": {
                "id": b.get("id"), "linha": b.get("linha"), "cod_it": cod_it,
                "lat": b.get("lat"), "lon": b.get("lon"),
                "em_movimento": b.get("em_movimento"), "vel_kmh": b.get("vel_kmh"),
                "rumo": b.get("direcao") if b.get("direcao") is not None else b.get("rumo"),
                "cor": b.get("cor") or (paradas[0].get("cor") if paradas else None),
                "destino": paradas[-1]["nome"] if paradas else None,
                "sentido": sentido, "previsao": previsao, "acessivel": acessivel,
            },
            "rota": pontos,
            "paradas": paradas,
        }

    # ------------------------------------------------------------ publicar HA
    def publicar_ha(self):
        """Espelha cada ônibus como device_tracker (compatível com o que já existia)."""
        with self.lock:
            lista = list(self.onibus.values())
        for b in lista:
            nome = self.nome_linha(b["linha"]) or b["linha"]
            payload = {
                "state": "Em movimento" if b["em_movimento"] else "Parado",
                "attributes": {
                    "latitude": b["lat"],
                    "longitude": b["lon"],
                    "friendly_name": f"{b['linha']} · {nome.title()}",
                    "linha": b["linha"],
                    "veiculo": b["id"],
                    "em_movimento": b["em_movimento"],
                    "velocidade_kmh": b.get("vel_kmh"),
                    "gps_accuracy": 15,
                    "source_type": "gps",
                    "icon": "mdi:bus",
                },
            }
            try:
                ha.definir_estado(f"device_tracker.bustracker_{b['id']}", payload["state"], payload["attributes"])
            except Exception as e:
                log.debug(f"não publiquei {b['id']}: {e}")

    def nome_linha(self, sigla):
        try:
            l = api.linha_por_sigla(sigla)
            return (l or {}).get("nom", "")
        except Exception:
            return ""

    def sigla_exib(self, sigla):
        """Sigla como o usuário conhece (085 em vez de 85)."""
        try:
            l = api.linha_por_sigla(sigla)
            return str((l or {}).get("sgl") or sigla)
        except Exception:
            return sigla

    # --------------------------------------------------------------- pessoas
    def pessoas_ha(self, ttl=60):
        """Pessoas e rastreadores disponíveis no HA + serviços de notificação."""
        agora = time.time()
        cache = getattr(self, "_cache_pessoas", None)
        if cache and (agora - cache[0]) < ttl:
            return cache[1]
        pessoas, rastreadores, notificacoes = [], [], []
        try:
            for s in ha.estados():
                eid = s.get("entity_id", "")
                if eid.startswith("person."):
                    pessoas.append({
                        "entity_id": eid,
                        "nome": s.get("attributes", {}).get("friendly_name") or eid,
                        "tem_gps": s.get("attributes", {}).get("latitude") is not None,
                    })
                elif eid.startswith("device_tracker.") and not eid.startswith("device_tracker.bustracker_"):
                    eid_txt = eid.replace("device_tracker.", "")
                    if "bustracker" in eid_txt or "bus_tracker" in eid_txt:
                        continue
                    rastreadores.append({
                        "entity_id": eid,
                        "nome": s.get("attributes", {}).get("friendly_name") or eid_txt,
                        "tem_gps": s.get("attributes", {}).get("latitude") is not None,
                    })
        except Exception as e:
            self.registrar(f"não consegui listar pessoas no HA: {e}", "warning")
        try:
            for dom in ha.servicos():
                if dom.get("domain") != "notify":
                    continue
                for srv in dom.get("services", {}):
                    if srv.startswith("mobile_app_"):
                        apelido = srv.replace("mobile_app_", "").replace("_", " ").title()
                        notificacoes.append({"servico": srv, "nome": apelido})
        except Exception as e:
            log.debug(f"serviços: {e}")
        self._cache_pessoas = (agora, (pessoas, rastreadores, notificacoes))
        return pessoas, rastreadores, notificacoes

    def posicao(self, entidade):
        st = ha.estado(entidade)
        if not st:
            return None
        a = st.get("attributes", {})
        lat, lon = a.get("latitude"), a.get("longitude")
        try:
            if lat is None or lon is None:
                return None
            return float(lat), float(lon)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------ alvo
    def _rotas_da_linha(self, sigla, limite=6):
        rotas = []
        for cod_it, _ in self.itinerarios.get(norm_sigla(sigla), {}).get("its", [])[:limite]:
            try:
                r = api.rota_do_itinerario(cod_it)
            except Exception:
                continue
            if r:
                rotas.append(r)
        return rotas

    def paradas_da_linha_perto(self, pos, sigla, alcance_m=600, passo_m=200):
        """Paradas COM coordenada da linha, perto da pessoa.

        A API só devolve paradas próximas de um ponto (raio curto), então
        varremos o traçado da linha na vizinhança da pessoa e ficamos com as
        paradas que realmente estão sobre esse traçado.
        """
        rotas = self._rotas_da_linha(sigla)
        if not rotas:
            return []
        rotas.sort(key=lambda r: r.projetar(pos)[1])
        vistas, achadas = set(), []
        for rota in rotas[:2]:
            s_p, off_p = rota.projetar(pos)
            if off_p > 20000:
                continue
            s = max(0.0, s_p - alcance_m)
            fim = min(rota.comprimento, s_p + alcance_m)
            while s <= fim:
                ponto = rota.ponto_em(s)
                try:
                    candidatas = api.paradas_proximas(ponto[0], ponto[1])
                except Exception:
                    candidatas = []
                for c in candidatas:
                    if c["cod"] in vistas:
                        continue
                    vistas.add(c["cod"])
                    try:
                        _, off = rota.projetar((c["lat"], c["lon"]))
                    except Exception:
                        continue
                    if off > 100:  # não é parada desta linha
                        continue
                    achadas.append({
                        "nome": c["nome"], "lat": c["lat"], "lon": c["lon"], "cod": c["cod"],
                        "dist_pessoa": geo.haversine(pos, (c["lat"], c["lon"])),
                    })
                s += passo_m
        achadas.sort(key=lambda x: x["dist_pessoa"])
        return achadas

    def alvo(self, pessoa, sigla, forcar=False):
        """Onde o ônibus encontra a pessoa: ponto do traçado mais próximo dela.

        Guarda também a parada oficial mais perto (quando existe a menos de
        500 m) para mostrar no aviso e no mapa. Cache de 10 min / 250 m.
        """
        chave = (pessoa["id"], norm_sigla(sigla))
        agora = time.time()
        pos = self.posicao(pessoa.get("entidade"))
        if not pos:
            return None
        guardado = self.alvos.get(chave)
        if guardado and not forcar:
            recente = (agora - guardado["ts"]) < 600
            perto = geo.haversine(pos, guardado["pos"]) < 250
            if recente and perto:
                return guardado

        alvo = {"ts": agora, "pos": pos, "parada": None, "passa_a_m": None}
        rotas = self._rotas_da_linha(sigla)
        melhor = None
        for rota in rotas:
            s, off = rota.projetar(pos)
            if melhor is None or off < melhor[1]:
                melhor = (s, off)
        if melhor:
            alvo["passa_a_m"] = melhor[1]
        try:
            for c in self.paradas_da_linha_perto(pos, sigla):
                if c["dist_pessoa"] <= 500:
                    alvo["parada"] = c
                break
        except Exception as e:
            self.registrar(f"parada de {pessoa['nome']} na linha {sigla}: {e}", "warning")
        self.alvos[chave] = alvo
        if alvo["parada"]:
            self.registrar(
                f"{pessoa['nome']} · linha {sigla}: ônibus passa a {_fmt_dist(alvo['passa_a_m'])} "
                f"· ponto {alvo['parada']['nome']} ({_fmt_dist(alvo['parada']['dist_pessoa'])})"
            )
        else:
            self.registrar(
                f"{pessoa['nome']} · linha {sigla}: ônibus passa a {_fmt_dist(alvo['passa_a_m'])} "
                "(sem parada oficial por perto)"
            )
        return alvo

    def s_do_alvo(self, alvo, rota):
        """Posição, no traçado informado, do ponto onde o ônibus encontra a pessoa."""
        if not alvo or not rota or not alvo.get("pos"):
            return None
        s, off = rota.projetar(alvo["pos"])
        if off > 2000:  # esta direção não passa perto da pessoa
            return None
        return s

    # -------------------------------------------------------------- avaliação
    def dentro_da_janela(self, regra, agora=None):
        agora = agora or datetime.now(_tz(self.cfg["ajustes"]["fuso"]))
        dias = regra.get("dias") or list(range(7))
        try:
            if agora.weekday() not in [int(d) for d in dias]:
                return False
        except (TypeError, ValueError):
            pass
        ini = (regra.get("inicio") or "00:00").strip()
        fim = (regra.get("fim") or "23:59").strip()
        try:
            h_ini, m_ini = [int(x) for x in ini.split(":")]
            h_fim, m_fim = [int(x) for x in fim.split(":")]
        except Exception:
            return True
        minutos = agora.hour * 60 + agora.minute
        ini_m, fim_m = h_ini * 60 + m_ini, h_fim * 60 + m_fim
        if ini_m <= fim_m:
            return ini_m <= minutos <= fim_m
        return minutos >= ini_m or minutos <= fim_m  # atravessa a meia-noite

    def candidatos(self, sigla, alvo, limiar_m, destino=None):
        """Ônibus da linha que ainda vão chegar no ponto, com ETA.

        Com `destino` (lat,lon), só entram os ônibus cujo itinerário passa no
        ponto E segue até o destino (ou seja, vão na direção certa).
        """
        saida = []
        with self.lock:
            lista = [dict(b) for b in self.onibus.values() if norm_sigla(b["linha"]) == norm_sigla(sigla)]
        vel_min = float(self.cfg["ajustes"].get("velocidade_min_kmh", 12))
        for b in lista:
            rota = None
            try:
                rota = api.rota_do_itinerario(b["cod_it"])
            except Exception:
                continue
            if not rota or b.get("s") is None:
                continue
            s_alvo = self.s_do_alvo(alvo, rota)
            if s_alvo is None or s_alvo <= b["s"] - 60:
                continue  # ponto já ficou para trás
            if destino is not None:
                s_dest, off_dest = rota.projetar(destino)
                if s_dest is None or off_dest > 2000:
                    continue  # esta direção não passa no destino
                if s_dest < s_alvo - 50:
                    continue  # destino fica atrás do ponto: direção errada
            d = s_alvo - b["s"]
            if d > limiar_m:
                continue
            vel = max(b.get("vel_kmh") or 0.0, vel_min)
            b["dist_ponto"] = d
            b["eta_min"] = round((d / 1000) / vel * 60, 1)
            b["rota"] = rota
            b["s_alvo"] = s_alvo
            saida.append(b)
        saida.sort(key=lambda x: x["dist_ponto"])
        return saida

    # ------------------------------------------------------------- trajetos
    def _tempo_pe_min(self, dist_m):
        """Tempo aproximado a pé (min) para uma distância em metros."""
        vel = float(self.cfg["ajustes"].get("velocidade_caminhada_kmh", 4.5)) or 4.5
        return (dist_m / 1000.0) / vel * 60.0

    def posicao_casa(self):
        """Posição da casa: entidade do HA (ex.: zone.home) ou lat/lon salvos."""
        casa = self.cfg.get("casa") or {}
        ent = (casa.get("entidade") or "").strip()
        if ent:
            st = ha.estado(ent)
            if st:
                a = st.get("attributes", {})
                if a.get("latitude") is not None and a.get("longitude") is not None:
                    try:
                        return (float(a["latitude"]), float(a["longitude"]))
                    except (TypeError, ValueError):
                        pass
        lat, lon = casa.get("lat"), casa.get("lon")
        if lat is not None and lon is not None:
            return (float(lat), float(lon))
        return None

    def _parada_mais_proxima(self, ref, linha):
        """(dist_m, parada) da parada oficial da linha mais próxima de `ref`."""
        cod = (linha or {}).get("cod")
        if cod is None:
            return None
        try:
            paradas = api.paradas_com_coordenadas(cod)
        except Exception as e:
            log.debug(f"paradas com coordenadas {cod}: {e}")
            return None
        melhor = None
        for p in paradas:
            d = geo.haversine(ref, (p["lat"], p["lon"]))
            if melhor is None or d < melhor[0]:
                melhor = (d, p)
        return melhor

    def _montar_ponto(self, ref, destino, nome, parada=None):
        """Monta o ponto de embarque (coords, caminhada por ruas, alvo)."""
        destino = (float(destino[0]), float(destino[1]))
        alvo = {"pos": destino, "parada": parada,
                "passa_a_m": round(geo.haversine(ref, destino))}
        info = None
        try:
            info = rotas_ruas.caminhada(ref, destino)
        except Exception:
            info = None
        if info:
            dist, caminho, fonte = info["dist_m"], info["pontos"], info["fonte"]
        else:
            fator = float(self.cfg["ajustes"].get("fator_rota", 1.3))
            dist = geo.haversine(ref, destino) * fator
            caminho, fonte = [list(ref), list(destino)], "reta"
        return {"nome": nome, "lat": destino[0], "lon": destino[1],
                "dist_m": round(dist), "tempo_min": round(self._tempo_pe_min(dist), 1),
                "caminho": caminho, "fonte": fonte, "alvo": alvo}

    def _ponto_trajeto(self, pessoa, sigla, ref_pos=None):
        """Ponto de embarque (parada mais próxima) a partir de uma referência.

        Devolve ponto, distância/tempo a pé (por ruas) e o traçado da caminhada.
        """
        ref = ref_pos or self.posicao(pessoa.get("entidade"))
        if not ref:
            return None
        # 1º) parada oficial que fica SOBRE o traçado que o ônibus percorre
        #     (mesma lógica do ETA/alvo), para o ponto bater com a rota desenhada
        parada = None
        try:
            perto = self.paradas_da_linha_perto(ref, sigla)
            if perto:
                parada = perto[0]
        except Exception as e:
            log.debug(f"paradas sobre o traçado {sigla}: {e}")
        # 2º) reserva: parada mais próxima da lista da linha (pode não estar na rota)
        if not parada:
            mp = self._parada_mais_proxima(ref, api.linha_por_sigla(sigla))
            if mp:
                parada = mp[1]
        if parada:
            return self._montar_ponto(ref, (parada["lat"], parada["lon"]), parada["nome"],
                                      parada=parada)
        # sem parada oficial: usa o ponto do traçado mais próximo
        melhor = None
        for rota in self._rotas_da_linha(sigla):
            s, off = rota.projetar(ref)
            if melhor is None or off < melhor[1]:
                melhor = (s, off, rota)
        if not melhor or melhor[1] > 3000:
            return None
        return self._montar_ponto(ref, melhor[2].ponto_em(melhor[0]), "onde o ônibus passa")

    def _ponto_trajeto_destino(self, pessoa, sigla, destino, ref_pos=None):
        """Parada de embarque ESTÁVEL no sentido do destino.

        Escolhe a parada mais próxima da pessoa que esteja antes do destino, em
        um itinerário que **passa no destino**. Depende só da pessoa + destino
        (não da posição do ônibus), então o ponto não fica pulando.
        """
        ref = ref_pos or self.posicao(pessoa.get("entidade"))
        if not ref:
            return None
        melhor = None  # (dist_pessoa, parada)
        vistos = set()
        for cod_it, _ in self.itinerarios.get(norm_sigla(sigla), {}).get("its", [])[:6]:
            try:
                rota = api.rota_do_itinerario(cod_it)
                paradas = api.paradas_do_itinerario(cod_it)
            except Exception:
                continue
            if not rota or not paradas:
                continue
            s_dest, off_dest = rota.projetar(destino)
            if s_dest is None or off_dest > 2000:
                continue  # esta direção não passa no destino
            for p in paradas:
                s_p, _ = rota.projetar((p["lat"], p["lon"]))
                if s_p is None or s_p > s_dest + 50:
                    continue  # parada depois do destino: sentido errado
                chave = p.get("cod") or (round(p["lat"], 5), round(p["lon"], 5))
                if chave in vistos:
                    continue
                vistos.add(chave)
                d = geo.haversine(ref, (p["lat"], p["lon"]))
                if melhor is None or d < melhor[0]:
                    melhor = (d, p)
        if not melhor:
            return None
        return self._montar_ponto(ref, (melhor[1]["lat"], melhor[1]["lon"]),
                                  melhor[1]["nome"], parada=melhor[1])

    def _risco(self, t_pessoa, t_bus, margem):
        if t_bus is None:
            return "sem-previsao"
        if t_bus + 0.001 < t_pessoa:
            return "perdeu"
        if t_bus - t_pessoa < margem:
            return "correr"
        return "ok"

    def _destino_trajeto(self, d, linhas=None):
        """Resolve o ponto de destino (por cod/nome nas linhas, ou coords salvas)."""
        if not d:
            return None
        tem_coord = d.get("lat") is not None and d.get("lon") is not None
        if not (d.get("cod") or d.get("nome") or tem_coord):
            return None
        achou = None
        if d.get("cod") or d.get("nome"):
            for sigla in (linhas or []):
                try:
                    linha = api.linha_por_sigla(sigla)
                except Exception:
                    linha = None
                if not linha:
                    continue
                try:
                    paradas = api.paradas_com_coordenadas(linha["cod"])
                except Exception as e:
                    log.debug(f"destino {sigla}: {e}")
                    continue
                for p in paradas:
                    if (d.get("cod") and str(p.get("cod")) == str(d.get("cod"))) or \
                       (d.get("nome") and p.get("nome") == d.get("nome")):
                        achou = p
                        break
                if achou:
                    break
        if not achou:
            achou = {"nome": d.get("nome") or "", "lat": d.get("lat"), "lon": d.get("lon"),
                     "cod": d.get("cod")}
        return {"nome": achou.get("nome") or "", "lat": achou.get("lat"),
                "lon": achou.get("lon"), "cod": achou.get("cod")}

    def calcular_trajeto(self, t):
        """Calcula ponto de embarque, caminhada, ônibus e risco de perder.

        Considera uma ou mais linhas; se o trajeto não tiver linha, usa as linhas
        já monitoradas (ou as que atendem o destino, conforme o ajuste).
        """
        pessoa = next((p for p in self.cfg.get("pessoas", []) if p["id"] == t.get("pessoa")), None)
        if not pessoa or not pessoa.get("ativo", True):
            return None
        linhas = self.linhas_do_trajeto(t)
        if not linhas:
            return None
        pos_pessoa = self.posicao(pessoa.get("entidade"))
        ref = pos_pessoa or self.posicao_casa()
        margem = float(self.cfg["ajustes"].get("margem_embarque_min", 2))
        limite = float(self.cfg["ajustes"].get("dist_max_embarque_m", 2000) or 0)
        destino = self._destino_trajeto(t.get("destino") or {}, linhas)
        destino_pos = None
        if destino and destino.get("lat") is not None and destino.get("lon") is not None:
            destino_pos = (destino["lat"], destino["lon"])
        if destino_pos:
            self._diag(t, f"destino {destino.get('nome')} ({destino_pos[0]:.5f},{destino_pos[1]:.5f}); "
                          f"linhas={', '.join(self.sigla_exib(s) for s in linhas)}")
        elif t.get("destino"):
            self._diag(t, f"destino '{t.get('destino')}' sem coordenadas — não dá para checar a direção")

        # ponto de embarque é o MESMO para todos os ônibus da linha (estável)
        coletados = []
        pontos_linha = []   # pontos válidos mesmo quando não há ônibus indo ao destino
        origem = ref
        for sigla in linhas:
            if destino_pos:
                try:
                    ponto = self._ponto_trajeto_destino(pessoa, sigla, destino_pos, ref_pos=ref)
                except Exception as e:
                    log.debug(f"trajeto {t.get('id')} linha {sigla} (destino): {e}")
                    ponto = None
            else:
                try:
                    ponto = self._ponto_trajeto(pessoa, sigla, ref_pos=ref)
                except Exception as e:
                    log.debug(f"trajeto {t.get('id')} linha {sigla}: {e}")
                    ponto = None
            if not ponto:
                self._diag(t, f"linha {self.sigla_exib(sigla)}: nenhuma parada no sentido do destino")
                continue
            if not origem:
                origem = ponto["alvo"]["pos"]
            pontos_linha.append((self.sigla_exib(sigla), ponto))
            candidatos = self.candidatos(sigla, ponto["alvo"], 10 ** 7, destino=destino_pos)
            self._diag(t, f"linha {self.sigla_exib(sigla)}: ponto '{ponto['nome']}' "
                          f"({ponto['dist_m']} m a pé) · {len(candidatos)} ônibus indo ao destino")
            for b in candidatos:
                eta = b.get("eta_min")
                risco = self._risco(ponto["tempo_min"], eta, margem)
                coletados.append({
                    "linha": self.sigla_exib(sigla),
                    "ponto": ponto,
                    "bus": {
                        "id": b["id"], "linha": self.sigla_exib(sigla),
                        "eta_min": eta, "dist_m": round(b.get("dist_ponto") or 0),
                        "risco": risco,
                        "tempo_total_min": eta if (eta is not None and risco != "perdeu") else None,
                    },
                })
        def montar(ponto, linha_principal, onibus, agora_bool, bus_id, bus_ids, longe):
            return {
                "id": t.get("id"), "pessoa": pessoa["nome"], "pessoa_id": pessoa["id"],
                "linhas": [self.sigla_exib(s) for s in linhas],
                "linha": linha_principal,
                "horarios": list(t.get("horarios") or []), "ativo": bool(t.get("ativo", True)),
                "pos": {"lat": origem[0], "lon": origem[1]} if origem
                       else {"lat": ponto["lat"], "lon": ponto["lon"]},
                "destino": destino,
                "agora": agora_bool, "longe": longe, "dist_max_m": limite,
                "bus_id": bus_id, "bus_ids": bus_ids,
                "ponto": {k: ponto[k] for k in ("nome", "lat", "lon", "dist_m", "tempo_min")},
                "caminho": ponto["caminho"], "fonte": ponto["fonte"],
                "onibus": onibus,
            }

        def dentro_da_janela():
            try:
                janela = float(self.cfg["ajustes"].get("janela_saida_min", 30))
                prox = self._proximo_horario(t, datetime.now(_tz(self.cfg["ajustes"]["fuso"])),
                                             depois_min=janela)
                if not prox:
                    self._diag(t, "fora do horário: nenhum horário para hoje "
                                  "(confira os dias da semana do trajeto)")
                    return False
                if prox[1] > janela:
                    self._diag(t, f"fora do horário: próximo às {prox[0]:%H:%M} "
                                  f"(faltam {prox[1]:.0f} min; janela {janela:.0f} min)")
                    return False
                return True
            except Exception:
                return False

        if not coletados:
            # sem ônibus indo ao destino agora. Se o ponto existe e está além do
            # limite de caminhada, mostramos o trajeto em cinza ("longe").
            if pontos_linha:
                sig_nome, ponto = min(pontos_linha, key=lambda x: x[1].get("dist_m") or 0)
                if limite > 0 and (ponto.get("dist_m") or 0) > limite:
                    info = montar(ponto, sig_nome, [], dentro_da_janela(), None, [], True)
                    self._log_trajeto(t, info)
                    return info
            self._log_trajeto(t, None)
            return None

        # prefere pontos dentro do limite de caminhada; depois o menor ETA
        coletados.sort(key=lambda x: (limite > 0 and (x["ponto"].get("dist_m") or 0) > limite,
                                      x["bus"]["eta_min"] is None,
                                      x["bus"]["eta_min"] if x["bus"]["eta_min"] is not None else 1e9))
        melhor = coletados[0]
        ponto = melhor["ponto"]
        longe = limite > 0 and (ponto.get("dist_m") or 0) > limite
        onibus, vistos = [], set()
        for c in coletados:
            if c["bus"]["id"] in vistos:
                continue
            vistos.add(c["bus"]["id"])
            onibus.append(c["bus"])
            if len(onibus) >= 3:
                break

        # destaca o próximo ônibus que vai passar no ponto indo ao destino,
        # INDEPENDENTE da janela de horário (a janela só controla os avisos).
        # Se o ponto estiver além do limite, não destaca — só cinza.
        agora_bool = dentro_da_janela()
        bus_id, bus_ids = None, []
        if not longe:
            bus_ids = [b["id"] for b in onibus]
            if onibus:
                bus_id = onibus[0]["id"]
        info = montar(ponto, melhor["linha"], onibus, agora_bool, bus_id, bus_ids, longe)
        self._log_trajeto(t, info)
        return info

    def avaliar_avisos(self):
        """Decide se algun ônibus está chegando e dispara o aviso."""
        agora = datetime.now(_tz(self.cfg["ajustes"]["fuso"]))
        pessoas = {p["id"]: p for p in self.cfg.get("pessoas", [])}
        limiar = float(self.cfg["ajustes"].get("limiar_aviso_m", 2500))
        cooldown = float(self.cfg["ajustes"].get("cooldown_min", 45)) * 60
        for regra in self.cfg.get("regras", []):
            if not regra.get("ativo"):
                continue
            if not self.dentro_da_janela(regra, agora):
                continue
            for pessoa_id in regra.get("pessoas", []):
                pessoa = pessoas.get(pessoa_id)
                if not pessoa or not pessoa.get("ativo", True):
                    continue
                alvo = self.alvo(pessoa, regra["linha"])
                if not alvo:
                    continue
                lista = self.candidatos(regra["linha"], alvo, limiar)
                if not lista:
                    continue
                b = lista[0]
                chave = (regra["id"], pessoa_id, b["id"])
                ultimo = self.avisos.get(chave, 0)
                if time.time() - ultimo < cooldown:
                    continue
                # "indo em direção": percorrendo o traçado para frente ou já parado perto
                hist = b.get("historico") or []
                avancando = True
                if len(hist) >= 2:
                    rota = b["rota"]
                    s_ant = None
                    try:
                        s_ant, _ = rota.projetar((hist[-2][1], hist[-2][2]))
                    except Exception:
                        s_ant = None
                    if s_ant is not None:
                        avancando = (b["s"] - s_ant) > -20
                if not avancando and b["dist_ponto"] > 400:
                    continue
                self.avisos[chave] = time.time()
                self.enviar_aviso(regra, pessoa, b, alvo)
        # limpa avisos velhos
        with self.lock:
            for chave, ts in list(self.avisos.items()):
                if time.time() - ts > 6 * 3600:
                    self.avisos.pop(chave, None)

    def _proximo_horario(self, trajeto, agora, depois_min=5):
        """Próximo horário do trajeto (datetime, minutos restantes) ou None.

        `depois_min` é a tolerância depois do horário (para o trajeto continuar
        "ativo" enquanto o ônibus ainda está chegando).
        """
        try:
            if agora.weekday() not in [int(d) for d in (trajeto.get("dias") or list(range(7)))]:
                return None
        except (TypeError, ValueError):
            pass
        melhor = None
        for h in trajeto.get("horarios") or []:
            m = _hhmm(h)
            if m is None:
                continue
            dt = agora.replace(hour=m // 60, minute=m % 60, second=0, microsecond=0)
            diff = (dt - agora).total_seconds() / 60.0
            if diff >= -depois_min and (melhor is None or diff < melhor[1]):
                melhor = (dt, diff)
        return melhor

    def avaliar_trajetos(self):
        """Avisa para sair a tempo e mantém o rastreio automático do trajeto."""
        agora = datetime.now(_tz(self.cfg["ajustes"]["fuso"]))
        janela = float(self.cfg["ajustes"].get("janela_saida_min", 30))
        cooldown = float(self.cfg["ajustes"].get("cooldown_min", 45)) * 60
        for t in self.cfg.get("trajetos", []):
            if not t.get("ativo", True):
                continue
            chave = str(t.get("id"))
            prox = self._proximo_horario(t, agora, depois_min=janela)
            if not prox or prox[1] > janela:
                # saiu da janela: encerra o rastreio automático desse trajeto
                if chave in self.rastreios:
                    self.parar_rastreio(chave, aviso=False)
                continue
            try:
                info = self.calcular_trajeto(t)
            except Exception as e:
                log.debug(f"trajeto {t.get('id')}: {e}")
                continue
            if not info or not info.get("onibus"):
                if chave in self.rastreios:
                    self.parar_rastreio(chave, aviso=False)
                continue
            b = info["onibus"][0]
            if b.get("risco") in ("correr", "perdeu"):
                aviso_chave = (t.get("id"), b["id"], "saida")
                if time.time() - self.avisos.get(aviso_chave, 0) >= cooldown:
                    self.avisos[aviso_chave] = time.time()
                    self.enviar_saida(info, b)
            # rastreio automático (Live Activity): começa quando o ônibus cumpre
            # as condições do trajeto e termina no tick (chegada/expiração/janela)
            if chave not in self.rastreios:
                self.iniciar_rastreio(info["pessoa_id"], b["linha"], b["id"],
                                      trajeto_id=t.get("id"), ponto=info["ponto"])

    # ------------------------------------------------------------ notificações
    def _notificar(self, pessoa, titulo, mensagem, extra=None, simulacao_tag=None):
        servico = (pessoa.get("notify") or "").replace("notify.", "")
        if not servico:
            self.registrar(f"{pessoa['nome']} sem serviço de notificação configurado", "warning")
            return False
        dados = {"title": titulo, "message": mensagem}
        if extra:
            dados["data"] = extra
        if self.cfg["ajustes"].get("simulacao"):
            self.registrar(f"[SIMULAÇÃO] {pessoa['nome']} ← {titulo} · {mensagem}")
            return True
        codigo = ha.chamar_servico("notify", servico, dados)
        if codigo and codigo >= 400:
            self.registrar(f"falha ao notificar {pessoa['nome']} (HTTP {codigo})", "error")
            return False
        return True

    def _texto_ponto(self, alvo, curto=False):
        """Complemento do aviso: ponto mais próximo ou onde o ônibus passa."""
        parada = alvo.get("parada") if alvo else None
        if parada:
            nome = parada["nome"]
            if curto and len(nome) > 32:
                nome = nome[:31].rstrip() + "…"
            return f"ponto {nome}", parada["dist_pessoa"]
        if alvo and alvo.get("passa_a_m") is not None:
            return f"passa a {_fmt_dist(alvo['passa_a_m'])}", alvo["passa_a_m"]
        return "", None

    def enviar_aviso(self, regra, pessoa, bus, alvo):
        eta = bus.get("eta_min")
        eta_txt = f"~{eta:.0f} min" if eta is not None else "chegando"
        complemento, _ = self._texto_ponto(alvo)
        msg = f"{eta_txt} até você" + (f" · {complemento}" if complemento else "")
        recusar = f"RECUSAR|{pessoa['id']}|{bus['linha']}|{bus['id']}"
        ok = self._notificar(
            pessoa,
            f"Ônibus {bus['linha']} chegando",
            msg,
            {
                "tag": f"onibus_aviso_{pessoa['id']}",
                "group": f"onibus_{pessoa['id']}",
                "channel": "Bus Tracker",
                "color": "#FFB300",
                "notification_icon": "mdi:bus",
                "interruption_level": "time-sensitive",
                "actions": [
                    {"action": recusar, "title": "Agora não"},
                ],
            },
        )
        if ok:
            self.registrar(f"Aviso enviado a {pessoa['nome']}: {bus['linha']} · {msg}")

    def _pessoa(self, pessoa_id):
        return next((p for p in self.cfg.get("pessoas", []) if p["id"] == pessoa_id), None)

    def enviar_saida(self, info, bus):
        """Avisa para sair de casa e ir ao ponto."""
        pessoa = self._pessoa(info["pessoa_id"])
        if not pessoa:
            return
        eta = bus.get("eta_min")
        caminhada = info["ponto"]["tempo_min"]
        if bus.get("risco") == "perdeu":
            titulo = f"Pode perder a linha {info['linha']}"
            msg = (f"Ônibus em ~{eta:.0f} min e você a ~{caminhada:.0f} min a pé. "
                   "Corra ou pegue o próximo.")
        else:
            titulo = f"Sai agora para pegar a linha {info['linha']}"
            msg = (f"Ônibus em ~{eta:.0f} min · ~{caminhada:.0f} min a pé "
                   f"até {info['ponto']['nome']}.")
        self._notificar(pessoa, titulo, msg, {
            "tag": f"trajeto_saida_{info['pessoa_id']}",
            "group": f"trajeto_{info['pessoa_id']}",
            "channel": "Bus Tracker",
            "color": "#3d7dff",
            "notification_icon": "mdi:walk",
            "interruption_level": "time-sensitive",
            "actions": [
                {"action": f"RECUSAR|{info['pessoa_id']}|{info['linha']}|{bus['id']}", "title": "Agora não"},
            ],
        })
        self.registrar(f"Saída sugerida a {info['pessoa']}: linha {info['linha']} · {msg}")

    def push_rastreio(self, pessoa, rastreio, bus, alvo, eta, d, primeiro=False):
        chave = rastreio.get("chave") or pessoa["id"]
        complemento, _ = self._texto_ponto(alvo, curto=True)
        msg = f"~{eta:.0f} min até você" if eta is not None else "chegando"
        if complemento:
            msg += f" · {complemento}"
        self._notificar(
            pessoa,
            f"Ônibus {bus['linha']}",
            msg,
            {
                "tag": f"onibus_rastreio_{chave}",
                "group": f"onibus_{chave}",
                "channel": "Bus Tracker",
                "live_update": True,
                "silent": not primeiro,        # iOS: atualização silenciosa
                "alert_once": not primeiro,    # Android: alerta só uma vez
                "sticky": True,                # Android: mantém ao tocar
                "notification_icon": "mdi:bus",
                "notification_icon_color": "#FFB300",  # iOS
                "color": "#FFB300",                      # Android
                "actions": [{"action": f"PARAR|{chave}", "title": "Parar rastreio"}],
            },
        )

    def push_chegou(self, pessoa, rastreio, bus, alvo, d):
        chave = rastreio.get("chave") or pessoa["id"]
        complemento, distancia = self._texto_ponto(alvo)
        onde = f"passa a {_fmt_dist(distancia or d)} de você" if complemento else f"a {_fmt_dist(d)}"
        self._notificar(
            pessoa,
            "🚌 Ônibus chegando!",
            f"Linha {bus['linha']} {onde}",
            {
                "tag": f"onibus_chegou_{chave}",
                "group": f"onibus_{chave}",
                "channel": "Bus Tracker",
                "color": "#4CAF50",
                "notification_icon": "mdi:bus",
                "interruption_level": "time-sensitive",
                "actions": [{"action": f"PARAR|{chave}", "title": "Encerrar rastreio"}],
            },
        )

    def limpar(self, pessoa, *tags):
        for tag in tags:
            self._notificar(pessoa, "", "clear_notification", {"tag": tag})

    # -------------------------------------------------------------- rastreio
    def iniciar_rastreio(self, pessoa_id, sigla, bus_id, trajeto_id=None, ponto=None):
        """Liga o rastreio automático de um trajeto (Live Activity)."""
        pessoas = {p["id"]: p for p in self.cfg.get("pessoas", [])}
        pessoa = pessoas.get(pessoa_id)
        if not pessoa:
            return False
        chave = str(trajeto_id or pessoa_id)
        with self.lock:
            if chave in self.rastreios:
                return True
        alvo = None
        if ponto:
            alvo = {"pos": (ponto["lat"], ponto["lon"]),
                    "parada": {"nome": ponto.get("nome") or "ponto",
                               "lat": ponto["lat"], "lon": ponto["lon"],
                               "dist_pessoa": ponto.get("dist_m")},
                    "passa_a_m": ponto.get("dist_m")}
        alvo = alvo or self.alvo(pessoa, sigla, forcar=True)
        with self.lock:
            bus = self.onibus.get(str(bus_id))
        d = None
        if bus and alvo and bus.get("s") is not None:
            for c in self.candidatos(sigla, alvo, 10 ** 7):
                if c["id"] == str(bus_id):
                    d = c["dist_ponto"]
                    break
        with self.lock:
            self.rastreios[chave] = {
                "chave": chave,
                "pessoa_id": pessoa_id,
                "trajeto_id": trajeto_id,
                "linha": sigla,
                "bus_id": str(bus_id),
                "inicio": time.time(),
                "ultimo_push": 0.0,
                "d0": d or 0,
                "ponto": ponto,
            }
        self.registrar(f"Rastreio automático: {pessoa['nome']} → linha {sigla} (veículo {bus_id})")
        return True

    def parar_rastreio(self, chave, aviso=True):
        with self.lock:
            r = self.rastreios.pop(str(chave), None)
        if not r:
            return False
        pessoas = {p["id"]: p for p in self.cfg.get("pessoas", [])}
        pessoa = pessoas.get(r.get("pessoa_id"))
        if pessoa:
            self.limpar(pessoa, f"onibus_rastreio_{chave}", f"onibus_chegou_{chave}")
            if aviso:
                self._notificar(pessoa, "Rastreio encerrado",
                                f"Você parou de acompanhar a linha {r['linha']}.",
                                {"tag": f"onibus_fim_{chave}"})
        self.registrar(f"Rastreio encerrado: {chave} (linha {r['linha']})")
        return True

    def tick_rastreios(self):
        """Atualiza os Live Activities automáticos em andamento."""
        with self.lock:
            ativos = list(self.rastreios.values())
        pessoas = {p["id"]: p for p in self.cfg.get("pessoas", [])}
        cadencia = float(self.cfg["ajustes"].get("atualizacao_rastreio_s", 90))
        for r in ativos:
            chave = r.get("chave") or r["pessoa_id"]
            pessoa = pessoas.get(r["pessoa_id"])
            if not pessoa:
                self.parar_rastreio(chave, aviso=False)
                continue
            if time.time() - r["inicio"] > RASTREIO_MAX_MIN * 60:
                self.registrar(f"Rastreio de {pessoa['nome']} expirou ({RASTREIO_MAX_MIN} min)")
                self.parar_rastreio(chave)
                continue
            with self.lock:
                bus = dict(self.onibus.get(r["bus_id"]) or {}) or None
            if not bus or (time.time() - bus.get("ts", 0)) > 300:
                # veículo sumiu: tenta assumir o próximo da mesma linha
                alvo = self._alvo_rastreio(pessoa, r)
                lista = self.candidatos(r["linha"], alvo, 10 ** 7) if alvo else []
                if lista:
                    novo = lista[0] if lista[0]["id"] != r["bus_id"] else (lista[1] if len(lista) > 1 else None)
                    if novo:
                        self.registrar(f"Veículo {r['bus_id']} saiu do mapa; seguindo {novo['id']}")
                        with self.lock:
                            if chave in self.rastreios:
                                self.rastreios[chave]["bus_id"] = novo["id"]
                                self.rastreios[chave]["d0"] = novo["dist_ponto"]
                        continue
                self.parar_rastreio(chave)
                continue
            alvo = self._alvo_rastreio(pessoa, r)
            if not alvo:
                continue
            rota = None
            try:
                rota = api.rota_do_itinerario(bus["cod_it"])
            except Exception:
                rota = None
            s_alvo = self.s_do_alvo(alvo, rota) if rota else None
            if s_alvo is None or bus.get("s") is None:
                continue
            d = max(0.0, s_alvo - bus["s"])
            vel = max(bus.get("vel_kmh") or 0.0, float(self.cfg["ajustes"].get("velocidade_min_kmh", 12)))
            eta = (d / 1000) / vel * 60
            if d <= CHEGADA_M:
                self.push_chegou(pessoa, r, bus, alvo, d)
                time.sleep(1.5)
                self.parar_rastreio(chave, aviso=False)
                continue
            if time.time() - r["ultimo_push"] >= cadencia or r["ultimo_push"] == 0:
                self.push_rastreio(pessoa, r, bus, alvo, eta, d)
                with self.lock:
                    if chave in self.rastreios:
                        self.rastreios[chave]["ultimo_push"] = time.time()
                        if not self.rastreios[chave]["d0"]:
                            self.rastreios[chave]["d0"] = d

    def _alvo_rastreio(self, pessoa, r):
        """Alvo do rastreio: o ponto do trajeto, se houver; senão o da linha."""
        ponto = r.get("ponto")
        if ponto and ponto.get("lat") is not None:
            return {"pos": (ponto["lat"], ponto["lon"]),
                    "parada": {"nome": ponto.get("nome") or "ponto",
                               "lat": ponto["lat"], "lon": ponto["lon"],
                               "dist_pessoa": ponto.get("dist_m")},
                    "passa_a_m": ponto.get("dist_m")}
        return self.alvo(pessoa, r["linha"])

    # --------------------------------------------------------------- eventos
    def tratar_evento(self, evento):
        if evento.get("event_type") != "mobile_app_notification_action":
            return
        acao = (evento.get("data") or {}).get("action") or ""
        partes = acao.split("|")
        if partes[0] == "PARAR" and len(partes) >= 2:
            self.parar_rastreio(partes[1])
        elif partes[0] == "RECUSAR":
            self.registrar(f"Aviso recusado pelo usuário ({acao})", "info")

    # ------------------------------------------------------------------ extra
    def rotas_render(self, max_pts=400):
        """Traçados das linhas observadas, simplificados, para desenhar no mapa."""
        saida = {}
        for sigla in self.linhas_observadas():
            its = self.itinerarios.get(sigla, {}).get("its", [])
            linhas = []
            for cod_it, _ in its[:6]:
                try:
                    rota = api.rota_do_itinerario(cod_it)
                except Exception:
                    continue
                if not rota:
                    continue
                passo = max(1, len(rota.pts) // max_pts)
                linhas.append([[round(p[0], 5), round(p[1], 5)] for p in rota.pts[::passo]])
            if linhas:
                saida[sigla] = linhas
        return saida

    def estado_publico(self, com_rotas=True):
        agora = time.time()
        pessoas_cfg = {p["id"]: p for p in self.cfg.get("pessoas", [])}
        with self.lock:
            onibus = []
            for b in self.onibus.values():
                idade = agora - b.get("ts", agora)
                onibus.append({
                    "id": b["id"], "linha": b["linha"], "lat": b["lat"], "lon": b["lon"],
                    "em_movimento": b["em_movimento"], "vel_kmh": b.get("vel_kmh"),
                    "cod_it": b.get("cod_it"),
                    "rumo": b.get("direcao") if b.get("direcao") is not None else b.get("rumo"),
                    "cor": b.get("cor"),
                    "visto_ha_s": round(idade),
                    "eta": None,
                })
            rastreios = [dict(r) for r in self.rastreios.values()]
        lugares = {}
        # todas as pessoas cadastradas (e ativas) que tenham GPS no HA
        for pid, pessoa in pessoas_cfg.items():
            if not pessoa.get("ativo", True):
                continue
            pos = self.posicao(pessoa.get("entidade"))
            if pos:
                lugares[pid] = {"nome": pessoa["nome"], "lat": pos[0], "lon": pos[1]}
        mapa = self.cfg.get("mapa", {})
        trajetos = []
        for t in self.cfg.get("trajetos", []):
            if not t.get("ativo", True):
                continue
            try:
                info = self.calcular_trajeto(t)
            except Exception:
                info = None
            if info:
                trajetos.append(info)
        pontos = []
        for (pid, sigla), alvo in list(self.alvos.items()):
            if not alvo.get("pos"):
                continue
            if sigla not in [norm_sigla(s) for s in mapa.get("onibus", [])] and pid not in mapa.get("pessoas", []):
                continue
            parada = alvo.get("parada")
            if parada:
                ponto = {"nome": parada["nome"], "lat": parada["lat"], "lon": parada["lon"],
                         "dist_pessoa": parada["dist_pessoa"]}
            else:
                # ponto do traçado onde o ônibus encontra a pessoa
                melhor = None
                for rota in self._rotas_da_linha(sigla):
                    s, off = rota.projetar(alvo["pos"])
                    if melhor is None or off < melhor[1]:
                        melhor = (s, off, rota)
                if not melhor or melhor[1] > 2000:
                    continue
                p = melhor[2].ponto_em(melhor[0])
                ponto = {"nome": "onde o ônibus passa", "lat": p[0], "lon": p[1],
                         "dist_pessoa": melhor[1]}
            ponto.update({"pessoa": pessoas_cfg.get(pid, {}).get("nome", pid),
                          "linha": self.sigla_exib(sigla),
                          "passa_a_m": alvo.get("passa_a_m")})
            pontos.append(ponto)
        return {
            "agora": agora,
            "ultimo_ciclo": self.ultimo_ciclo,
            "erro": self.erro_ciclo,
            "onibus": sorted(onibus, key=lambda x: (x["linha"], x["id"])),
            "lugares": list(lugares.values()),
            "pontos": pontos,
            "trajetos": trajetos,
            "casa": (lambda p, c: {"lat": p[0], "lon": p[1], "raio": c.get("raio", 150)}
                     if p else None)(self.posicao_casa(), self.cfg.get("casa") or {}),
            "rotas": self.rotas_render() if (com_rotas and mapa.get("rotas")) else {},
            "rastreios": rastreios,
            "log": list(self.log)[:60],
            "avisos_recentes": [
                {"regra": k[0], "pessoa": k[1], "bus": k[2], "quando": ts}
                for k, ts in sorted(self.avisos.items(), key=lambda kv: -kv[1])[:10]
            ],
        }
