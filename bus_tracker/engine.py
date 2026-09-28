"""Motor: observa os ônibus, decide os avisos e conduz o rastreio ao vivo."""

import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import geo
import ha
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
                    "primeira_vez": antigo is None,
                }
                if antigo:
                    novo["historico"] = antigo.get("historico", [])[-6:]
                    novo["vel_kmh"] = antigo.get("vel_kmh", 0.0)
                    novo["s"] = antigo.get("s")
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
                "interruption_level": "time-sensitive",
                "actions": [
                    {"action": acao, "title": "📡 Rastrear"},
                    {"action": recusar, "title": "Agora não"},
                ],
            },
        )
        if ok:
            self.registrar(f"Aviso enviado a {pessoa['nome']}: {bus['linha']} · {msg}")

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
                "live_update": True,
                "silent": not primeiro,
                "critical_text": _fmt_dist(d),
                "progress": pct,
                "progress_max": 100,
                "notification_icon": "mdi:bus",
                "notification_icon_color": "#FFB300",
                "progress_bar_color": "#FFB300",
            },
        )

    def push_chegou(self, pessoa, bus, alvo, d):
        complemento, distancia = self._texto_ponto(alvo)
        onde = f"passa a {_fmt_dist(distancia or d)} de você" if complemento else f"a {_fmt_dist(d)}"
        self._notificar(
            pessoa,
            "🚌 Ônibus chegando!",
            f"Linha {bus['linha']} {onde}",
            {"tag": f"onibus_chegou_{pessoa['id']}", "interruption_level": "time-sensitive"},
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
                {"tag": f"onibus_parar_{pessoa['id']}",
                 "actions": [{"action": f"PARAR|{pessoa_id}", "title": "Parar rastreio"}]},
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
                    "visto_ha_s": round(idade),
                    "eta": None,
                })
            rastreios = [dict(r) for r in self.rastreios.values()]
        lugares = {}
        mapa = self.cfg.get("mapa", {})
        for pid in mapa.get("pessoas", []):
            pessoa = pessoas_cfg.get(pid)
            if not pessoa:
                continue
            pos = self.posicao(pessoa.get("entidade"))
            if pos:
                lugares[pid] = {"nome": pessoa["nome"], "lat": pos[0], "lon": pos[1]}
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
            "rotas": self.rotas_render() if (com_rotas and mapa.get("rotas")) else {},
            "rastreios": rastreios,
            "log": list(self.log)[:60],
            "avisos_recentes": [
                {"regra": k[0], "pessoa": k[1], "bus": k[2], "quando": ts}
                for k, ts in sorted(self.avisos.items(), key=lambda kv: -kv[1])[:10]
            ],
        }
