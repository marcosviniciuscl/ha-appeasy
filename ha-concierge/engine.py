"""Deterministic monitoring. LLM output is never an action authorization."""
import datetime as dt
import statistics
import threading
import time


VALID = {"unknown", "unavailable", "none", ""}
OPEN = {"on", "open", "detected"}
CRITICAL_CLASSES = {"gas", "smoke", "moisture", "problem"}
METER_CLASSES = {"energy", "power", "water", "gas"}


def fresh(state, minutes=120):
    if str(state.get("state", "")).lower() in VALID:
        return False
    try:
        stamp = dt.datetime.fromisoformat(state.get("last_updated", "").replace("Z", "+00:00"))
        return (dt.datetime.now(dt.timezone.utc) - stamp).total_seconds() <= minutes * 60
    except (ValueError, TypeError):
        return False


def snapshot(states, areas, entities, devices):
    area_by_id = {a.get("area_id"): a.get("name") for a in areas}
    device_area = {d.get("id"): d.get("area_id") for d in devices}
    registry = {e.get("entity_id"): e for e in entities}
    result = []
    for s in states:
        eid = s.get("entity_id", "")
        reg = registry.get(eid, {})
        area_id = reg.get("area_id") or device_area.get(reg.get("device_id"))
        result.append({"entity_id": eid, "name": s.get("attributes", {}).get("friendly_name", eid),
                       "domain": eid.split(".")[0], "state": s.get("state"),
                       "unit": s.get("attributes", {}).get("unit_of_measurement"),
                       "device_class": s.get("attributes", {}).get("device_class"),
                       "area": area_by_id.get(area_id), "last_updated": s.get("last_updated"),
                       "active": fresh(s), "available": str(s.get("state", "")).lower() not in VALID})
    counts = {}
    for item in result:
        counts[item["domain"]] = counts.get(item["domain"], 0) + 1
    return {"areas": [{"id": a.get("area_id"), "name": a.get("name"),
                        "entity_count": sum(1 for e in result if e["area"] == a.get("name"))}
                       for a in areas], "entities": result, "counts": counts,
            "area_count": len(areas), "active_count": sum(e["active"] for e in result),
            "unavailable_count": sum(not e["available"] for e in result)}


def mode(states, presence_ids, manual):
    if manual in ("home", "away"):
        return manual, "definido manualmente"
    selected = [s for s in states if s.get("entity_id") in presence_ids]
    valid = [s for s in selected if fresh(s)]
    if not valid:
        return "unknown", "sem sensores de presença válidos"
    if any(str(s.get("state", "")).lower() in ("home", "on") for s in valid):
        return "home", "sensor de presença indica alguém em casa"
    if len(valid) != len(presence_ids):
        return "unknown", "parte dos sensores de presença está indisponível"
    if all(s.get("entity_id", "").startswith(("person.", "device_tracker."))
           and str(s.get("state", "")).lower() in ("not_home", "away") for s in valid):
        return "away", "pessoas e rastreadores selecionados indicam ausência"
    return "unknown", "sensores não confirmam ausência"


def anomaly(value, prior, factor=2.5):
    if len(prior) < 8:
        return False
    baseline = statistics.median(prior)
    if baseline <= 0:
        return False
    return value > baseline * factor


class Engine:
    def __init__(self, ha, store):
        self.ha, self.store = ha, store
        self.stop = threading.Event()
        self.last = {}
        self.last_alert = {}
        self.states = []
        self.error = None
        self.presence = ("unknown", "sem dados")
        self.on_security_alert = None

    def run(self):
        while not self.stop.is_set():
            try:
                self.tick()
                self.error = None
            except Exception as exc:
                self.error = str(exc)
            self.stop.wait(15)

    def alert(self, key, kind, title, detail, entity_id=None, severity="warning", cooldown=1800):
        now = time.time()
        if severity != "critical" and entity_id and now < self.store.get("muted:" + entity_id, 0):
            return
        if now - self.last_alert.get(key, 0) < cooldown:
            return
        self.last_alert[key] = now
        self.store.event(kind, title, detail, entity_id, severity)
        if self.store.get("notifications_enabled", False):
            try:
                self.ha.call_service("persistent_notification", "create",
                                     {"title": "HA Concierge: " + title, "message": detail,
                                      "notification_id": "ha_concierge_" + str(abs(hash(key)))})
            except Exception:
                self.store.event("notification", "Falha ao enviar aviso", title, entity_id)
        if kind in ("absence", "safety") and self.on_security_alert:
            self.on_security_alert(entity_id, kind)

    def tick(self):
        states = self.ha.states()
        self.states = states
        chosen = set(self.store.get("selected", []))
        self.presence = mode(states, self.store.get("presence_entities", []),
                             self.store.get("manual_mode", "auto"))
        for s in states:
            eid = s.get("entity_id", "")
            if eid not in chosen or not fresh(s):
                continue
            value = str(s.get("state", ""))
            previous = self.last.get(eid)
            attrs = s.get("attributes", {})
            dclass = attrs.get("device_class", "")
            if previous is None:
                self.last[eid] = value
            elif previous != value:
                self.last[eid] = value
                self.store.event("change", attrs.get("friendly_name", eid),
                                 f"{previous} → {value}", eid)
                self._routine(eid, value)
            if dclass in CRITICAL_CLASSES and value.lower() in OPEN:
                self.alert(eid + value, "safety", "Sensor de segurança ativado",
                           f"{eid} informa {value}. Verifique no local.", eid, "critical")
            if (dclass in ("door", "window", "opening") and value.lower() in OPEN
                    and self.presence[0] == "away"):
                self.alert(eid + "away", "absence", "Abertura durante ausência",
                           f"{eid} está {value}; {self.presence[1]}.", eid)
            if dclass in METER_CLASSES:
                try:
                    number = float(value)
                except ValueError:
                    continue
                unit = attrs.get("unit_of_measurement", "")
                samples = self.store.samples(eid, 48)
                if attrs.get("state_class") == "total_increasing":
                    if samples:
                        delta = number - samples[0]["value"]
                        if delta < 0:
                            delta = 0  # meter reset
                        prior = [max(0, samples[i]["value"] - samples[i+1]["value"])
                                 for i in range(len(samples)-1)]
                        if anomaly(delta, prior):
                            self.alert(eid + "meter", "consumption", "Consumo acima do padrão",
                                       f"{eid}: variação {delta:.2f} {unit} em 15 min; compare com histórico.", eid)
                elif anomaly(number, [x["value"] for x in samples]):
                    self.alert(eid + "meter", "consumption", "Leitura acima do padrão",
                               f"{eid}: {number:.2f} {unit}; acima da mediana recente.", eid)
                if not samples or time.time() - samples[0]["ts"] >= 15 * 60:
                    self.store.sample(eid, number, unit)
        self._execute_schedules()

    def _routine(self, eid, value):
        if not eid.startswith(("light.", "switch.")) or value not in ("on", "off"):
            return
        now = dt.datetime.now().astimezone()
        history = self.store.events(300)
        days = {dt.datetime.fromtimestamp(e["ts"]).date() for e in history
                if e["kind"] == "change" and e["entity_id"] == eid
                and e["detail"].endswith("→ " + value)
                and abs(dt.datetime.fromtimestamp(e["ts"]).hour - now.hour) <= 1}
        if len(days) >= 3:
            service = "turn_on" if value == "on" else "turn_off"
            self.store.proposal(eid, f"{service} {eid} diariamente",
                                f"Ação observada em {len(days)} dias perto de {now.hour:02d}h. Revise antes de aprovar.",
                                {"hour": now.hour, "minute": now.minute, "domain": eid.split(".")[0],
                                 "service": service, "entity_id": eid})

    def _execute_schedules(self):
        now = dt.datetime.now().astimezone()
        today = now.date().isoformat()
        for p in self.store.proposals():
            if p["status"] != "approved":
                continue
            import json
            cfg = json.loads(p["payload"])
            if (cfg["hour"], cfg["minute"]) != (now.hour, now.minute):
                continue
            key = f"schedule:{p['id']}:{today}"
            if self.store.get(key):
                continue
            self.store.set(key, True)
            if cfg["entity_id"] not in self.store.get("selected", []):
                continue
            try:
                self.ha.call_service(cfg["domain"], cfg["service"], {"entity_id": cfg["entity_id"]})
                self.store.event("automation", p["title"], "Execução concluída", cfg["entity_id"])
            except Exception:
                self.store.event("automation", p["title"], "Falha na execução", cfg["entity_id"], "warning")
