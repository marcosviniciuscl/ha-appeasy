"""Local visual fixture: CONCIERGE_DATA=/tmp/... python tests/demo_server.py."""
import datetime as dt
import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("CONCIERGE_DATA", "/tmp/ha-concierge-demo")
os.environ["CONCIERGE_DEV"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


now = dt.datetime.now(dt.timezone.utc).isoformat()
def item(eid, value, name, kind=None):
    attrs = {"friendly_name": name}
    if kind:
        attrs["device_class"] = kind
    return {"entity_id": eid, "state": value, "last_updated": now, "attributes": attrs}

app.ha.states = lambda: [
    item("person.marcos", "home", "Marcos"),
    item("binary_sensor.porta_entrada", "off", "Porta de entrada", "door"),
    item("binary_sensor.movimento_sala", "off", "Movimento sala", "motion"),
    item("sensor.energia", "0.7", "Potência total", "power"),
    item("sensor.agua", "12.6", "Consumo de água", "water"),
    item("light.sala", "on", "Luz da sala"),
    item("light.cozinha", "off", "Luz da cozinha"),
    item("camera.entrada", "idle", "Câmera da entrada"),
    item("sensor.temperatura", "25.1", "Temperatura da sala", "temperature"),
]
app.ha.areas = lambda: [{"area_id": "sala", "name": "Sala"}, {"area_id": "cozinha", "name": "Cozinha"},
                        {"area_id": "entrada", "name": "Entrada"}, {"area_id": "quarto", "name": "Quarto"}]
app.ha.entity_registry = lambda: [
    {"entity_id": eid, "area_id": area} for eid, area in [
        ("person.marcos", "sala"), ("binary_sensor.porta_entrada", "entrada"),
        ("binary_sensor.movimento_sala", "sala"), ("sensor.energia", "sala"),
        ("sensor.agua", "cozinha"), ("light.sala", "sala"),
        ("light.cozinha", "cozinha"), ("camera.entrada", "entrada"),
        ("sensor.temperatura", "sala")]]
app.ha.device_registry = lambda: []
app.ha.history = lambda ids, hours: [[{"entity_id": eid, "state": "normal", "last_updated": now}] for eid in ids]
app.engine.tick()
ThreadingHTTPServer(("0.0.0.0", 8099), app.Handler).serve_forever()
