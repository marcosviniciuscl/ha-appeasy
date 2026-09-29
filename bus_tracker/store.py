"""Persistência em /data (sobrevive a reinícios e atualizações do App)."""

import json
import logging
import os
import tempfile

log = logging.getLogger("bus_tracker.store")

DIR_DADOS = os.environ.get("DIR_DADOS", "/data")
ARQ_CONFIG = os.path.join(DIR_DADOS, "bus_tracker.json")


def _padroes():
    return {
        "ajustes": {
            "limiar_aviso_m": 2500,       # avisa quando faltar menos que isso até o ponto
            "cooldown_min": 45,           # tempo mínimo entre avisos do mesmo ônibus
            "velocidade_min_kmh": 12,     # usada para o ETA quando o ônibus está parado
            "fuso": "",                   # vazio = usa o fuso da cidade escolhida
            "intervalo_segundos": 30,
            "atualizacao_rastreio_s": 90, # cadência do Live Activity
            "simulacao": False,           # true = não envia nada, só registra no log
            "diagnostico": False,         # true = loga detalhes dos trajetos (debug)
            "velocidade_caminhada_kmh": 4.5,  # velocidade média a pé
            "fator_rota": 1.3,                # ruas ≈ 30% mais que a linha reta
            "margem_embarque_min": 2,         # chegar com essa folga no ponto
            "janela_saida_min": 30,           # avalia trajetos nessa janela antes do horário
            "osrm_base": "https://routing.openstreetmap.de/routed-foot",  # roteamento a pé
            "raio_destino_m": 3000,       # raio p/ achar pontos ao marcar o destino no mapa
            "dist_max_embarque_m": 2000,  # limite de caminhada até o ponto de embarque
            # trajeto sem linha: "monitoradas" = linhas já monitoradas no app;
            # "cidade" = descobre linhas da cidade que atendem o destino
            "trajetos_sem_linha": "monitoradas",
        },
        "cidade": {},
        "casa": {"entidade": "zone.home", "lat": None, "lon": None, "raio": 150},
        "pessoas": [],
        "regras": [],
        "trajetos": [],
        "mapa": {"onibus": [], "pessoas": [], "rotas": True, "pontos": True},
        "historico": [],
    }


def carregar():
    cfg = _padroes()
    if os.path.exists(ARQ_CONFIG):
        try:
            with open(ARQ_CONFIG, encoding="utf-8") as f:
                salvo = json.load(f)
            for chave, valor in salvo.items():
                if isinstance(valor, dict) and isinstance(cfg.get(chave), dict):
                    cfg[chave].update(valor)
                else:
                    cfg[chave] = valor
        except Exception as e:
            log.error(f"config corrompida, usando padrões: {e}")
    # migra o roteador antigo (linha reta por ruas "driving") para o a pé
    if cfg["ajustes"].get("osrm_base") == "https://router.project-osrm.org":
        cfg["ajustes"]["osrm_base"] = "https://routing.openstreetmap.de/routed-foot"
    return cfg


def salvar(cfg):
    os.makedirs(DIR_DADOS, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=DIR_DADOS, prefix=".bustracker-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ARQ_CONFIG)
        return True
    except Exception as e:
        log.error(f"falha ao salvar config: {e}")
        return False
