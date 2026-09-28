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
        self.trajeto_ts = {}      # trajeto_id -> ts do último push de tempo real

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
        for t in self.cfg.get("trajetos", []):
            if t.get("ativo", True) and t.get("linha"):
                siglas.add(norm_sigla(t.get("linha")))
        siglas.discard("")
        return sorted(siglas)

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

    def candidatos(self, sigla, alvo, limiar_m):
        """Ônibus da linha que ainda vão chegar no ponto da pessoa, com ETA."""
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

    def _ponto_trajeto(self, pessoa, sigla, ref_pos=None):
        """Ponto de embarque (parada mais próxima) a partir de uma referência.

        Devolve ponto, distância/tempo a pé (por ruas) e o traçado da caminhada.
        """
        ref = ref_pos or self.posicao(pessoa.get("entidade"))
        if not ref:
            return None
        linha = api.linha_por_sigla(sigla)
        parada = None
        mp = self._parada_mais_proxima(ref, linha)
        if mp:
            parada = mp[1]
        if parada:
            destino, nome = (parada["lat"], parada["lon"]), parada["nome"]
        else:
            # sem parada oficial: usa o ponto do traçado mais próximo
            melhor = None
            for rota in self._rotas_da_linha(sigla):
                s, off = rota.projetar(ref)
                if melhor is None or off < melhor[1]:
                    melhor = (s, off, rota)
            if not melhor or melhor[1] > 3000:
                return None
            destino, nome = melhor[2].ponto_em(melhor[0]), "onde o ônibus passa"
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

    def _risco(self, t_pessoa, t_bus, margem):
        if t_bus is None:
            return "sem-previsao"
        if t_bus + 0.001 < t_pessoa:
            return "perdeu"
        if t_bus - t_pessoa < margem:
            return "correr"
        return "ok"

    def calcular_trajeto(self, t):
        """Calcula ponto, caminhada, ônibus e risco de perder para um trajeto.

        `ida`: sai de casa -> ponto perto da casa (zona `casa`).
        `volta`: pega perto de onde a pessoa está e desce perto da casa.
        """
        pessoa = next((p for p in self.cfg.get("pessoas", []) if p["id"] == t.get("pessoa")), None)
        if not pessoa or not pessoa.get("ativo", True):
            return None
        sentido = t.get("sentido") or "ida"
        casa = self.posicao_casa()
        pos_pessoa = self.posicao(pessoa.get("entidade"))
        ref = casa if (sentido == "ida" and casa) else None
        ponto = self._ponto_trajeto(pessoa, t.get("linha"), ref_pos=ref)
        if not ponto:
            return None
        origem = casa if (sentido == "ida" and casa) else (pos_pessoa or ponto["alvo"]["pos"])
        margem = float(self.cfg["ajustes"].get("margem_embarque_min", 2))
        onibus = []
        for b in self.candidatos(t.get("linha"), ponto["alvo"], 10 ** 7)[:3]:
            eta = b.get("eta_min")
            risco = self._risco(ponto["tempo_min"], eta, margem)
            onibus.append({
                "id": b["id"], "eta_min": eta, "dist_m": round(b.get("dist_ponto") or 0),
                "risco": risco,
                "tempo_total_min": eta if (eta is not None and risco != "perdeu") else None,
            })
        # volta: também calcula onde descer (ponto perto da casa) e a caminhada
        destino_casa = None
        if sentido == "volta" and casa:
            dp = self._ponto_trajeto(pessoa, t.get("linha"), ref_pos=casa)
            if dp:
                destino_casa = {"nome": dp["nome"], "lat": dp["lat"], "lon": dp["lon"],
                                "dist_m": dp["dist_m"], "tempo_min": dp["tempo_min"],
                                "caminho": dp["caminho"]}
        return {
            "id": t.get("id"), "pessoa": pessoa["nome"], "pessoa_id": pessoa["id"],
            "linha": self.sigla_exib(t.get("linha")), "sentido": sentido,
            "horarios": list(t.get("horarios") or []), "ativo": bool(t.get("ativo", True)),
            "pos": {"lat": origem[0], "lon": origem[1]},
            "casa": destino_casa,
            "ponto": {k: ponto[k] for k in ("nome", "lat", "lon", "dist_m", "tempo_min")},
            "caminho": ponto["caminho"], "fonte": ponto["fonte"],
            "onibus": onibus,
        }

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

    def _proximo_horario(self, trajeto, agora):
        """Próximo horário do trajeto (datetime, minutos restantes) ou None."""
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
            if diff >= -5 and (melhor is None or diff < melhor[1]):
                melhor = (dt, diff)
        return melhor

    def avaliar_trajetos(self):
        """Avisa para sair a tempo e mantém o tempo real (ônibus x caminhada)."""
        agora = datetime.now(_tz(self.cfg["ajustes"]["fuso"]))
        janela = float(self.cfg["ajustes"].get("janela_saida_min", 30))
        cooldown = float(self.cfg["ajustes"].get("cooldown_min", 45)) * 60
        cadencia = float(self.cfg["ajustes"].get("atualizacao_rastreio_s", 90))
        for t in self.cfg.get("trajetos", []):
            if not t.get("ativo", True):
                continue
            prox = self._proximo_horario(t, agora)
            if not prox or prox[1] > janela:
                continue
            try:
                info = self.calcular_trajeto(t)
            except Exception as e:
                log.debug(f"trajeto {t.get('id')}: {e}")
                continue
            if not info or not info.get("onibus"):
                continue
            b = info["onibus"][0]
            if b.get("risco") in ("correr", "perdeu"):
                chave = (t.get("id"), b["id"], "saida")
                if time.time() - self.avisos.get(chave, 0) >= cooldown:
                    self.avisos[chave] = time.time()
                    self.enviar_saida(info, b)
            # tempo real (com cadência para não estourar o iOS)
            tid = t.get("id")
            if time.time() - self.trajeto_ts.get(tid, 0) >= cadencia:
                self.trajeto_ts[tid] = time.time()
                self.push_trajeto(info, b)

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
        acao = f"RASTREAR|{pessoa['id']}|{bus['linha']}|{bus['id']}"
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
                    {"action": acao, "title": "📡 Rastrear"},
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
                {"action": f"RASTREAR|{info['pessoa_id']}|{info['linha']}|{bus['id']}", "title": "📡 Rastrear"},
                {"action": f"RECUSAR|{info['pessoa_id']}|{info['linha']}|{bus['id']}", "title": "Agora não"},
            ],
        })
        self.registrar(f"Saída sugerida a {info['pessoa']}: linha {info['linha']} · {msg}")

    def push_trajeto(self, info, bus):
        """Tempo real: ônibus x caminhada e risco de perder."""
        pessoa = self._pessoa(info["pessoa_id"])
        if not pessoa:
            return
        eta = bus.get("eta_min")
        caminhada = info["ponto"]["tempo_min"]
        risco = {"ok": "dá tempo", "correr": "corra!", "perdeu": "pode perder",
                 "sem-previsao": "sem previsão"}.get(bus.get("risco"), "")
        msg = f"Ônibus {info['linha']} em ~{eta:.0f} min · você {caminhada:.0f} min a pé · {risco}"
        self._notificar(pessoa, f"Linha {info['linha']} · {info['ponto']['nome']}", msg, {
            "tag": f"trajeto_{info['pessoa_id']}",
            "group": f"trajeto_{info['pessoa_id']}",
            "channel": "Bus Tracker",
            "color": "#3d7dff",
            "notification_icon": "mdi:bus-clock",
            "live_update": True,
            "alert_once": True,
            "silent": True,
            "critical_text": f"você {caminhada:.0f} min",
            "actions": [{"action": f"RASTREAR|{info['pessoa_id']}|{info['linha']}|{bus['id']}",
                         "title": "📡 Rastrear"}],
        })

    def push_rastreio(self, pessoa, rastreio, bus, alvo, eta, d, primeiro=False):
        pct = 0
        if rastreio.get("d0"):
            pct = int(max(0, min(100, round((1 - d / rastreio["d0"]) * 100))))
        complemento, _ = self._texto_ponto(alvo, curto=True)
        msg = f"~{eta:.0f} min até você" if eta is not None else "chegando"
        if complemento:
            msg += f" · {complemento}"
        self._notificar(
            pessoa,
            f"Ônibus {bus['linha']}",
            msg,
            {
                "tag": f"onibus_rastreio_{pessoa['id']}",
                "group": f"onibus_{pessoa['id']}",
                "channel": "Bus Tracker",
                "live_update": True,
                "silent": not primeiro,        # iOS: atualização silenciosa
                "alert_once": not primeiro,    # Android: alerta só uma vez
                "sticky": True,                # Android: mantém ao tocar
                "critical_text": _fmt_dist(d),
                "progress": pct,
                "progress_max": 100,
                "notification_icon": "mdi:bus",
                "notification_icon_color": "#FFB300",  # iOS
                "progress_bar_color": "#FFB300",        # iOS
                "color": "#FFB300",                      # Android
                "actions": [{"action": f"PARAR|{pessoa['id']}", "title": "Parar rastreio"}],
            },
        )

    def push_chegou(self, pessoa, bus, alvo, d):
        complemento, distancia = self._texto_ponto(alvo)
        onde = f"passa a {_fmt_dist(distancia or d)} de você" if complemento else f"a {_fmt_dist(d)}"
        self._notificar(
            pessoa,
            "🚌 Ônibus chegando!",
            f"Linha {bus['linha']} {onde}",
            {
                "tag": f"onibus_chegou_{pessoa['id']}",
                "group": f"onibus_{pessoa['id']}",
                "channel": "Bus Tracker",
                "color": "#4CAF50",
                "notification_icon": "mdi:bus",
                "interruption_level": "time-sensitive",
                "actions": [{"action": f"PARAR|{pessoa['id']}", "title": "Encerrar rastreio"}],
            },
        )

    def limpar(self, pessoa, *tags):
        for tag in tags:
            self._notificar(pessoa, "", "clear_notification", {"tag": tag})

    # -------------------------------------------------------------- rastreio
    def iniciar_rastreio(self, pessoa_id, sigla, bus_id, manual=False):
        pessoas = {p["id"]: p for p in self.cfg.get("pessoas", [])}
        pessoa = pessoas.get(pessoa_id)
        if not pessoa:
            return False
        alvo = self.alvo(pessoa, sigla, forcar=True)
        with self.lock:
            bus = self.onibus.get(str(bus_id))
        d = None
        if bus and alvo and bus.get("s") is not None:
            lista = self.candidatos(sigla, alvo, 10 ** 7)
            for c in lista:
                if c["id"] == str(bus_id):
                    d = c["dist_ponto"]
                    break
        with self.lock:
            self.rastreios[pessoa_id] = {
                "pessoa_id": pessoa_id,
                "linha": sigla,
                "bus_id": str(bus_id),
                "inicio": time.time(),
                "ultimo_push": 0.0,
                "d0": d or 0,
                "manual": manual,
            }
        self.registrar(f"Rastreio iniciado: {pessoa['nome']} → linha {sigla} (veículo {bus_id})")
        if bus and alvo:
            self._notificar(
                pessoa,
                f"📡 Rastreando a linha {sigla}",
                "Vou atualizar na sua tela de bloqueio.",
                {
                    "tag": f"onibus_parar_{pessoa['id']}",
                    "group": f"onibus_{pessoa['id']}",
                    "channel": "Bus Tracker",
                    "color": "#FFB300",
                    "notification_icon": "mdi:bus",
                    "sticky": True,
                    "actions": [{"action": f"PARAR|{pessoa_id}", "title": "Parar rastreio"}],
                },
            )
        return True

    def parar_rastreio(self, pessoa_id, aviso=True):
        with self.lock:
            r = self.rastreios.pop(pessoa_id, None)
        if not r:
            return False
        pessoas = {p["id"]: p for p in self.cfg.get("pessoas", [])}
        pessoa = pessoas.get(pessoa_id)
        if pessoa:
            self.limpar(pessoa, f"onibus_rastreio_{pessoa_id}", f"onibus_parar_{pessoa_id}")
            if aviso:
                self._notificar(pessoa, "Rastreio encerrado",
                                f"Você parou de acompanhar a linha {r['linha']}.",
                                {"tag": f"onibus_fim_{pessoa_id}"})
        self.registrar(f"Rastreio encerrado: {pessoa_id} (linha {r['linha']})")
        return True

    def tick_rastreios(self):
        """Atualiza os Live Activities em andamento."""
        with self.lock:
            ativos = list(self.rastreios.values())
        pessoas = {p["id"]: p for p in self.cfg.get("pessoas", [])}
        cadencia = float(self.cfg["ajustes"].get("atualizacao_rastreio_s", 90))
        for r in ativos:
            pessoa = pessoas.get(r["pessoa_id"])
            if not pessoa:
                self.parar_rastreio(r["pessoa_id"], aviso=False)
                continue
            if time.time() - r["inicio"] > RASTREIO_MAX_MIN * 60:
                self.registrar(f"Rastreio de {pessoa['nome']} expirou ({RASTREIO_MAX_MIN} min)")
                self.parar_rastreio(pessoa["id"])
                continue
            with self.lock:
                bus = dict(self.onibus.get(r["bus_id"]) or {}) or None
            if not bus or (time.time() - bus.get("ts", 0)) > 300:
                # veículo sumiu: tenta assumir o próximo da mesma linha
                alvo = self.alvo(pessoa, r["linha"])
                lista = self.candidatos(r["linha"], alvo, 10 ** 7) if alvo else []
                if lista:
                    novo = lista[0] if lista[0]["id"] != r["bus_id"] else (lista[1] if len(lista) > 1 else None)
                    if novo:
                        self.registrar(f"Veículo {r['bus_id']} saiu do mapa; seguindo {novo['id']}")
                        with self.lock:
                            self.rastreios[pessoa["id"]]["bus_id"] = novo["id"]
                            self.rastreios[pessoa["id"]]["d0"] = novo["dist_ponto"]
                        continue
                self.parar_rastreio(pessoa["id"])
                continue
            alvo = self.alvo(pessoa, r["linha"])
            if not alvo or not alvo.get("parada"):
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
                self.push_chegou(pessoa, bus, alvo, d)
                time.sleep(1.5)
                self.parar_rastreio(pessoa["id"], aviso=False)
                continue
            if time.time() - r["ultimo_push"] >= cadencia or r["ultimo_push"] == 0:
                self.push_rastreio(pessoa, r, bus, alvo, eta, d)
                with self.lock:
                    if pessoa["id"] in self.rastreios:
                        self.rastreios[pessoa["id"]]["ultimo_push"] = time.time()
                        if not self.rastreios[pessoa["id"]]["d0"]:
                            self.rastreios[pessoa["id"]]["d0"] = d

    # --------------------------------------------------------------- eventos
    def tratar_evento(self, evento):
        if evento.get("event_type") != "mobile_app_notification_action":
            return
        acao = (evento.get("data") or {}).get("action") or ""
        partes = acao.split("|")
        if partes[0] == "RASTREAR" and len(partes) >= 4:
            self.iniciar_rastreio(partes[1], partes[2], partes[3])
        elif partes[0] == "PARAR" and len(partes) >= 2:
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
