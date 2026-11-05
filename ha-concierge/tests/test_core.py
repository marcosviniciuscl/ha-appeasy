import datetime as dt
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Engine, anomaly, fresh, mode, snapshot
from store import Store


def item(eid, value, device_class=None):
    return {"entity_id": eid, "state": value,
            "last_updated": dt.datetime.now(dt.timezone.utc).isoformat(),
            "attributes": {"device_class": device_class} if device_class else {}}


class FakeHA:
    def __init__(self, states):
        self.values = states
        self.calls = []

    def states(self):
        return self.values

    def call_service(self, domain, service, data):
        self.calls.append((domain, service, data))


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as folder:
        yield Store(str(Path(folder) / "db.sqlite"))


def test_snapshot_counts_registry_areas_and_freshness():
    s = [item("sensor.power", "100", "power"), item("camera.front", "unavailable")]
    data = snapshot(s, [{"area_id": "a", "name": "Sala"}],
                    [{"entity_id": "sensor.power", "area_id": "a"}], [])
    assert data["area_count"] == 1
    assert data["areas"][0]["entity_count"] == 1
    assert data["active_count"] == 1
    assert data["unavailable_count"] == 1
    assert not fresh(s[1])


def test_presence_does_not_assume_away_from_missing_data():
    assert mode([], ["person.alex"], "auto")[0] == "unknown"
    assert mode([item("person.alex", "not_home")], ["person.alex"], "auto")[0] == "away"
    assert mode([item("binary_sensor.motion", "off")], ["binary_sensor.motion"], "auto")[0] == "unknown"
    assert mode([], [], "away")[0] == "away"


def test_away_opening_alert_and_no_unselected_camera_access(store):
    store.set("selected", ["binary_sensor.door", "person.alex"])
    store.set("presence_entities", ["person.alex"])
    ha = FakeHA([item("person.alex", "not_home"), item("binary_sensor.door", "on", "door")])
    engine = Engine(ha, store)
    engine.tick()
    assert engine.presence[0] == "away"
    assert [e for e in store.events() if e["kind"] == "absence"]
    assert not ha.calls
    engine.tick()
    assert len([e for e in store.events() if e["kind"] == "absence"]) == 1


def test_critical_alert_not_suppressed_by_feedback(store):
    store.set("selected", ["binary_sensor.smoke"])
    store.set("muted:binary_sensor.smoke", 9999999999)
    ha = FakeHA([item("binary_sensor.smoke", "on", "smoke")])
    Engine(ha, store).tick()
    assert store.events()[0]["severity"] == "critical"


def test_notifications_are_opt_in(store):
    store.set("selected", ["binary_sensor.smoke"])
    ha = FakeHA([item("binary_sensor.smoke", "on", "smoke")])
    Engine(ha, store).tick()
    assert not ha.calls
    store.set("notifications_enabled", True)
    Engine(ha, store).tick()
    assert ha.calls[0][0:2] == ("persistent_notification", "create")


def test_memory_file_tracks_saved_and_forgotten_preferences(store):
    path = store.data_dir / "identity" / "MEMORY.md"
    assert (store.data_dir / "identity" / "SOUL.md").exists()
    mid = store.remember("preference", "Luzes baixas à noite")
    assert "Luzes baixas à noite" in path.read_text()
    store.forget(mid)
    assert "Luzes baixas à noite" not in path.read_text()


def test_anomaly_needs_baseline():
    assert not anomaly(100, [10, 11])
    assert anomaly(100, [10]*8)
    assert not anomaly(11, [10]*8)


def test_proposal_requires_approval_and_can_be_disabled(store):
    pid = store.proposal("light.sala", "Luz", "Rotina", {"hour": 19, "minute": 0,
                         "domain": "light", "service": "turn_off", "entity_id": "light.sala"})
    with pytest.raises(ValueError):
        store.proposal_status(pid, "disabled")
    store.proposal_status(pid, "approved")
    store.proposal_status(pid, "disabled")
    assert store.proposals()[0]["status"] == "disabled"
