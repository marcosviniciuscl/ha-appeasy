import importlib
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_first_run_selection_and_permissions():
    with tempfile.TemporaryDirectory() as folder:
        os.environ["CONCIERGE_DATA"] = folder
        os.environ["CONCIERGE_DEV"] = "1"
        import app
        importlib.reload(app)
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        app.ha.states = lambda: [{"entity_id": "sensor.energy", "state": "4.2", "last_updated": now,
                                  "attributes": {"friendly_name": "Energia", "device_class": "power"}},
                                 {"entity_id": "camera.front", "state": "idle", "last_updated": now,
                                  "attributes": {"friendly_name": "Entrada"}}]
        app.ha.areas = lambda: [{"area_id": "living", "name": "Sala"}]
        app.ha.entity_registry = lambda: [{"entity_id": "sensor.energy", "area_id": "living"}]
        app.ha.device_registry = lambda: []
        app.ha.history = lambda ids, hours: [[{"entity_id": "sensor.energy", "state": "4.2", "last_updated": now}]]
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}/api/"
        headers = {"X-Requested-With": "HA-Concierge"}
        try:
            boot = requests.get(base + "bootstrap").json()
            assert not boot["profile"]["onboarded"]
            data = requests.get(base + "inventory").json()
            assert data["area_count"] == 1
            assert data["active_count"] == 2
            assert data["recent"]["sensor.energy"]["state"] == "4.2"
            response = requests.post(base + "select", json={"selected": ["sensor.energy"]}, headers=headers)
            assert response.status_code == 200
            assert requests.get(base + "bootstrap").json()["selected"] == ["sensor.energy"]
            assert requests.post(base + "camera/analyze", json={"entity_id": "camera.front"},
                                 headers=headers).status_code == 400
            assert requests.post(base + "profile", json={"assistant_name": "Casa", "onboarded": True},
                                 headers=headers).json()["assistant_name"] == "Casa"
            assert requests.post(base + "select", json={"selected": []}).status_code == 403
        finally:
            server.shutdown()
            server.server_close()
