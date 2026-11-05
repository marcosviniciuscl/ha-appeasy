"""Small Home Assistant REST/WebSocket client. Tokens never leave this process."""
import datetime as dt
import os
import json
import requests


class HAError(Exception):
    pass


class HAClient:
    def __init__(self, base=None, token=None, ws_url=None):
        self.base = (base or os.getenv("HA_BASE", "http://supervisor/core/api")).rstrip("/")
        self.token = token or os.getenv("HA_TOKEN") or os.getenv("SUPERVISOR_TOKEN", "")
        self.ws_url = ws_url or os.getenv("HA_WS", "ws://supervisor/core/websocket")

    def _request(self, method, path, **kwargs):
        if not self.token:
            raise HAError("Token do Home Assistant não disponível")
        try:
            res = requests.request(method, self.base + path,
                                   headers={"Authorization": "Bearer " + self.token},
                                   timeout=15, **kwargs)
            res.raise_for_status()
            return res.json() if res.content else None
        except requests.RequestException as exc:
            raise HAError("Falha na comunicação com o Home Assistant") from exc

    def states(self):
        return self._request("GET", "/states")

    def history(self, entity_ids, hours=24):
        if not entity_ids:
            return []
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat()
        return self._request("GET", "/history/period/" + since,
                             params={"filter_entity_id": ",".join(entity_ids),
                                     "minimal_response": "true", "no_attributes": "true"})

    def call_service(self, domain, service, data):
        return self._request("POST", f"/services/{domain}/{service}", json=data)

    def camera_snapshot(self, entity_id):
        if not entity_id.startswith("camera."):
            raise HAError("Entidade não é câmera")
        try:
            res = requests.get(self.base + "/camera_proxy/" + entity_id,
                               headers={"Authorization": "Bearer " + self.token}, timeout=12)
            res.raise_for_status()
            if len(res.content) > 4_000_000:
                raise HAError("Imagem grande demais")
            return res.content, res.headers.get("Content-Type", "image/jpeg")
        except requests.RequestException as exc:
            raise HAError("Não foi possível capturar imagem") from exc

    def ws_command(self, command):
        try:
            import websocket
            ws = websocket.create_connection(self.ws_url, timeout=10)
            try:
                greeting = json.loads(ws.recv())
                if greeting.get("type") != "auth_required":
                    raise HAError("Handshake WebSocket inesperado")
                ws.send(json.dumps({"type": "auth", "access_token": self.token}))
                auth = json.loads(ws.recv())
                if auth.get("type") != "auth_ok":
                    raise HAError("Autenticação WebSocket recusada")
                ws.send(json.dumps({"id": 1, "type": command}))
                result = json.loads(ws.recv())
                if not result.get("success"):
                    raise HAError("Comando WebSocket não disponível")
                return result.get("result", [])
            finally:
                ws.close()
        except HAError:
            raise
        except Exception as exc:
            raise HAError("Registro de áreas indisponível") from exc

    def areas(self):
        return self.ws_command("config/area_registry/list")

    def entity_registry(self):
        return self.ws_command("config/entity_registry/list")

    def device_registry(self):
        return self.ws_command("config/device_registry/list")
