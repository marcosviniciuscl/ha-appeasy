"""Deterministic suggestions derived only from discovered Home Assistant entities."""
from collections import defaultdict

PRIORITY = {"high": 0, "medium": 1, "low": 2}
METER_UNITS = {"kwh", "wh", "w", "kw", "m3", "m³", "l", "liters", "gal"}


def _names(entities, limit=3):
    names = [item.get("name") or item.get("entity_id") for item in entities[:limit]]
    text = ", ".join(names)
    if len(entities) > limit:
        text += f" e mais {len(entities) - limit}"
    return text


def _add(items, key, title, detail, reason, kind, action, action_label, priority, entities=None):
    items.append({
        "id": key,
        "title": title,
        "detail": detail,
        "reason": reason,
        "kind": kind,
        "action": action,
        "action_label": action_label,
        "priority": priority,
        "entities": [item.get("entity_id") for item in (entities or [])[:6]],
    })


def _meter(entity):
    unit = str(entity.get("unit") or "").lower()
    return entity.get("device_class") in ("energy", "power", "water", "gas") or unit in METER_UNITS


def build(data, selected, presence_entities, camera_allowed, camera_cloud,
          notifications_enabled, proposals):
    entities = data.get("entities") or []
    chosen = set(selected or [])
    presence = set(presence_entities or [])
    allowed = set(camera_allowed or [])
    items = []

    if not entities:
        _add(items, "sem-entidades", "Nenhuma entidade encontrada",
             "Confira se o Home Assistant está acessível e se há integrações carregando entidades.",
             "O inventário atual não retornou entidades.", "system", "monitor",
             "Revisar monitoramento", "high")
        return items

    by_domain = defaultdict(list)
    for entity in entities:
        by_domain[entity.get("domain", "")].append(entity)

    active = [entity for entity in entities if entity.get("active")]
    if not chosen:
        _add(items, "selecionar", "Escolha o que deve ser monitorado",
             f"O Home Assistant informa {len(active)} entidades ativas de {len(entities)} encontradas. "
             "O Concierge só observa o que você selecionar.",
             "Sugestão baseada no inventário atual.", "monitor", "monitor",
             "Escolher entidades", "high", active)

    critical = [entity for entity in entities
                if entity.get("device_class") in ("gas", "smoke", "moisture", "problem")]
    openings = [entity for entity in entities
                if entity.get("device_class") in ("door", "window", "opening")]
    meters = [entity for entity in entities if _meter(entity)]

    important_selected = [entity for entity in critical + openings + meters
                          if entity.get("entity_id") in chosen]
    if important_selected and not notifications_enabled:
        _add(items, "avisos", "Ative avisos para alertas importantes",
             f"{_names(important_selected)} já estão monitorados. Ative as notificações persistentes "
             "para receber avisos no Home Assistant quando algo exigir atenção.",
             "Há entidades monitoradas que podem gerar alertas.", "security",
             "settings-notifications", "Ativar avisos", "high", important_selected)

    missing_critical = [entity for entity in critical if entity.get("entity_id") not in chosen]
    if missing_critical:
        _add(items, "seguranca", "Monitore sensores de segurança",
             f"{_names(missing_critical)} podem indicar gás, fumaça, umidade ou falha. "
             "Selecione-os para receber alertas críticos.",
             "Sensores de segurança foram encontrados, mas ainda não estão selecionados.",
             "security", "monitor", "Selecionar sensores", "high", missing_critical)

    presence_candidates = [
        entity for entity in entities
        if entity.get("domain") in ("person", "device_tracker")
        or (entity.get("domain") == "binary_sensor"
            and entity.get("device_class") in ("motion", "occupancy", "presence"))
    ]
    if presence_candidates and not presence:
        _add(items, "presenca", "Configure a presença da casa",
             f"Encontramos {_names(presence_candidates)}. Sem uma fonte de presença, "
             "o App não conclui ausência e não gera alertas de abertura durante ausência.",
             "Pessoas ou sensores de presença foram encontrados.", "presence",
             "settings-presence", "Configurar presença", "high", presence_candidates)

    missing_openings = [entity for entity in openings if entity.get("entity_id") not in chosen]
    if chosen and missing_openings:
        _add(items, "aberturas", "Monitore portas e janelas",
             f"{_names(missing_openings)} permitem detectar abertura durante ausência e "
             "mudanças de estado relevantes.",
             "Sensores de abertura foram encontrados.", "security", "monitor",
             "Selecionar aberturas", "medium", missing_openings)

    missing_meters = [entity for entity in meters if entity.get("entity_id") not in chosen]
    if chosen and missing_meters:
        _add(items, "consumo", "Acompanhe consumo e possíveis anomalias",
             f"{_names(missing_meters)} podem ser monitorados para comparar com a mediana "
             "recente e destacar consumo atípico.",
             "Medidores de energia, água ou gás foram encontrados.", "energy", "monitor",
             "Selecionar medidores", "medium", missing_meters)

    lights = by_domain.get("light", []) + by_domain.get("switch", [])
    selected_lights = [entity for entity in lights if entity.get("entity_id") in chosen]
    missing_lights = [entity for entity in lights if entity.get("entity_id") not in chosen]
    if chosen and missing_lights:
        _add(items, "rotinas", "Descubra rotinas de luzes e interruptores",
             f"Há {len(lights)} luzes ou interruptores. Ao monitorá-los, o App observa horários "
             "repetidos e pode propor uma rotina diária para sua aprovação.",
             "Luzes e interruptores podem gerar propostas de rotina.", "automation",
             "monitor", "Selecionar luzes", "medium", missing_lights)
    elif selected_lights and not proposals:
        _add(items, "rotinas-observacao", "Rotinas em observação",
             "As luzes e interruptores selecionados estão sendo observados. Uma proposta "
             "aparece após três dias com ação em horário semelhante.",
             "Ainda não há propostas de rotina.", "automation", "automations",
             "Ver automações", "low", selected_lights)

    cameras = by_domain.get("camera", [])
    if chosen and cameras:
        selected_cameras = [entity for entity in cameras if entity.get("entity_id") in chosen]
        if not selected_cameras:
            _add(items, "cameras", "Selecione câmeras para análise sob demanda",
                 f"{_names(cameras)} podem ser analisadas apenas quando você pedir, "
                 "sem gravação contínua.",
                 "Câmeras foram encontradas.", "camera", "monitor",
                 "Selecionar câmeras", "low", cameras)
        elif not allowed:
            _add(items, "cameras-consentimento", "Autorize o uso de câmeras com consentimento",
                 "As câmeras selecionadas ainda não têm permissão de análise. A captura só "
                 "acontece sob demanda e com autorização explícita.",
                 "Câmeras selecionadas sem permissão de análise.", "camera",
                 "settings-cameras", "Revisar câmeras", "medium", selected_cameras)
        elif not camera_cloud:
            _add(items, "cameras-envio", "Envio externo de imagens está desligado",
                 "Você autorizou câmeras, mas o envio de imagens ao provedor está desativado. "
                 "Ative apenas se quiser análise visual externa.",
                 "Análise visual local ou externa depende do provedor configurado.", "camera",
                 "settings-cameras", "Revisar permissão", "low", selected_cameras)

    climate = [entity for entity in entities
               if entity.get("domain") in ("climate", "weather")
               or entity.get("device_class") in ("temperature", "humidity")]
    missing_climate = [entity for entity in climate if entity.get("entity_id") not in chosen]
    if chosen and missing_climate:
        _add(items, "clima", "Acompanhe conforto e clima",
             f"{_names(missing_climate)} podem ajudar a entender temperatura e umidade "
             "nos ambientes.",
             "Sensores de clima ou conforto foram encontrados.", "monitor", "monitor",
             "Selecionar clima", "low", missing_climate)

    low_battery = []
    for entity in entities:
        if entity.get("device_class") != "battery":
            continue
        try:
            value = float(entity.get("state"))
        except (TypeError, ValueError):
            continue
        if value <= 20:
            low_battery.append(entity)
    if low_battery:
        _add(items, "baterias", "Baterias com carga baixa",
             f"{_names(low_battery)} estão com 20% ou menos. Verifique a substituição.",
             "Sensores com classe de bateria foram encontrados.", "maintenance",
             "monitor", "Revisar baterias", "medium", low_battery)

    unavailable = [entity for entity in entities if not entity.get("available")]
    if unavailable:
        _add(items, "indisponiveis", "Entidades indisponíveis",
             f"{len(unavailable)} entidades estão indisponíveis ou sem estado válido: "
             f"{_names(unavailable)}. Revise a integração ou o dispositivo.",
             "O inventário contém entidades sem estado válido.", "maintenance",
             "monitor", "Revisar entidades", "low", unavailable)

    items.sort(key=lambda item: PRIORITY.get(item["priority"], 9))
    return items[:8]
