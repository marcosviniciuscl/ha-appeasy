#!/usr/bin/env python3
"""Bus Tracker — rastreio de ônibus ao vivo (SIUMobile) com painel no HA.

Funciona com qualquer cidade que use o sistema SIUMobile (TACOM/CIT-Siu); a
cidade é escolhida nas opções do App. Roda o ciclo de leitura da API, decide os
avisos de aproximação, conduz o rastreio ao vivo (Live Activity no iPhone) e
serve o painel web (aba do Home Assistant via ingress).
"""

import json
import logging
import os
import re
import signal
import sys
import threading
import time

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("bus_tracker")

import store
from engine import Motor
import ha
import rotas
import siumobile as api
import webapp

OPTIONS_FILE = "/data/options.json"

INTERVALO_INGRESS = int(os.environ.get("INGRESS_PORT") or os.environ.get("PORTA_WEB") or 8099)


def opcoes_app():
    if os.path.exists(OPTIONS_FILE):
        try:
            with open(OPTIONS_FILE) as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"options.json inválido: {e}")
    return {}


def laco_poll(motor, intervalo_fn):
    while True:
        t0 = time.monotonic()
        try:
            motor.ciclo()
            motor.publicar_ha()
            motor.avaliar_avisos()
            motor.avaliar_trajetos()
        except Exception as e:
            log.exception(f"erro no ciclo: {e}")
            motor.registrar(f"erro no ciclo: {e}", "error")
        intervalo = max(5, int(intervalo_fn()))
        espera = max(3, intervalo - (time.monotonic() - t0))
        time.sleep(espera)


def laco_rastreio(motor):
    while True:
        try:
            motor.tick_rastreios()
        except Exception as e:
            log.exception(f"erro no rastreio: {e}")
        time.sleep(15)


def main():
    cfg = store.carregar()
    opcoes = opcoes_app()

    salva = cfg.get("cidade") if isinstance(cfg.get("cidade"), dict) else None
    if salva and salva.get("chave"):
        # Escolha feita no painel tem prioridade sobre as opções do App.
        api.configurar(cidade=salva["chave"], base=salva.get("base"),
                       praca=salva.get("praca"), pacote=salva.get("pacote"))
    else:
        api.configurar(
            cidade=opcoes.get("cidade") or None,
            base=opcoes.get("api_base") or None,
            praca=opcoes.get("api_praca") or None,
            pacote=opcoes.get("app_package") or None,
        )
    cidade = api.cidade_atual()
    if not cfg["ajustes"].get("fuso"):
        cfg["ajustes"]["fuso"] = api.fuso_da_cidade() or "America/Sao_Paulo"

    if opcoes.get("intervalo_segundos"):
        cfg["ajustes"]["intervalo_segundos"] = int(opcoes["intervalo_segundos"])
    rotas.configurar(cfg["ajustes"].get("osrm_base"))
    linhas_brutas = opcoes.get("linhas_monitoradas") or []
    if not isinstance(linhas_brutas, (list, tuple, set)):
        linhas_brutas = re.split(r"[,;\s]+", str(linhas_brutas))
    linhas_extras = [str(s).strip() for s in linhas_brutas if str(s).strip()]
    motor = Motor(cfg, store.salvar, linhas_extras=linhas_extras)

    if not ha.token():
        log.error("Sem token do Supervisor: confira 'homeassistant_api: true' no config.yaml")
        sys.exit(1)

    motor.registrar(f"Bus Tracker 3.0 iniciando — {cidade['nome']}: painel, avisos e rastreio ao vivo")
    log.info(f"Cidade: {cidade['nome']} ({cidade['base']})")
    log.info(f"Linhas extras (opções do App): {linhas_extras or 'nenhuma'}")

    escutador = ha.Escutador(motor.tratar_evento)
    escutador.start()

    threading.Thread(target=laco_poll, args=(motor, lambda: cfg["ajustes"].get("intervalo_segundos", 30)),
                     daemon=True, name="poll").start()
    threading.Thread(target=laco_rastreio, args=(motor,), daemon=True, name="rastreio").start()

    httpd = webapp.criar(motor, INTERVALO_INGRESS, escutador)

    def desligar(*_):
        log.info("encerrando…")
        try:
            httpd.shutdown()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, desligar)
    signal.signal(signal.SIGINT, desligar)

    log.info(f"Painel disponível via ingress na porta {INTERVALO_INGRESS}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        desligar()


if __name__ == "__main__":
    main()
