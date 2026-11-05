"""Local SQLite storage. No camera images or credentials in the event log."""
import json
import os
import shutil
import sqlite3
import threading
import time
from pathlib import Path


class Store:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.data_dir = Path(path).parent
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL,
              entity_id TEXT, title TEXT NOT NULL, detail TEXT NOT NULL,
              severity TEXT NOT NULL DEFAULT 'info', dismissed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS samples (
              id INTEGER PRIMARY KEY, ts REAL NOT NULL, entity_id TEXT NOT NULL,
              value REAL NOT NULL, unit TEXT);
            CREATE TABLE IF NOT EXISTS memories (
              id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL,
              content TEXT NOT NULL, source TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS proposals (
              id INTEGER PRIMARY KEY, ts REAL NOT NULL, entity_id TEXT NOT NULL,
              title TEXT NOT NULL, detail TEXT NOT NULL, payload TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending');
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
            CREATE INDEX IF NOT EXISTS idx_samples_entity_ts ON samples(entity_id, ts);
            """)
            self.db.commit()
        if not self.get("profile"):
            self.set("profile", {"assistant_name": "Concierge", "resident_name": "", "onboarded": False})
        if self.get("selected") is None:
            self.set("selected", [])
        if self.get("camera_allowed") is None:
            self.set("camera_allowed", [])
        identity_dir = self.data_dir / "identity"
        identity_dir.mkdir(exist_ok=True)
        templates = Path(__file__).parent / ".agents"
        for name in ("SOUL.md", "AGENT.md"):
            target = identity_dir / name
            if not target.exists():
                shutil.copyfile(templates / name, target)
        self._sync_memory_file()

    def _sync_memory_file(self):
        lines = ["# Memória do HA Concierge", "", "Gerada pelo App. Edite preferências pela interface.", ""]
        for memory in self.memories():
            content = memory["content"].replace("\n", " ").replace("\r", " ")
            lines.append(f"- [{memory['kind']}] {content}")
        target = self.data_dir / "identity" / "MEMORY.md"
        temporary = target.with_suffix(".tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(temporary, target)

    def get(self, key, default=None):
        with self.lock:
            row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))
            self.db.commit()

    def event(self, kind, title, detail, entity_id=None, severity="info"):
        with self.lock:
            cur = self.db.execute("INSERT INTO events(ts,kind,entity_id,title,detail,severity) VALUES (?,?,?,?,?,?)",
                                  (time.time(), kind, entity_id, title, detail, severity))
            self.db.commit()
            return cur.lastrowid

    def events(self, limit=100):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]

    def dismiss(self, event_id):
        with self.lock:
            self.db.execute("UPDATE events SET dismissed=1 WHERE id=?", (event_id,))
            self.db.commit()

    def sample(self, entity_id, value, unit):
        with self.lock:
            self.db.execute("INSERT INTO samples(ts,entity_id,value,unit) VALUES (?,?,?,?)",
                            (time.time(), entity_id, value, unit))
            self.db.execute("DELETE FROM samples WHERE ts < ?", (time.time()-30*86400,))
            self.db.commit()

    def samples(self, entity_id, limit=50):
        with self.lock:
            return [dict(r) for r in self.db.execute(
                "SELECT * FROM samples WHERE entity_id=? ORDER BY id DESC LIMIT ?", (entity_id, limit))]

    def remember(self, kind, content, source="user", confirmed=True):
        with self.lock:
            cur = self.db.execute("INSERT INTO memories(ts,kind,content,source,confirmed) VALUES (?,?,?,?,?)",
                                  (time.time(), kind, content, source, int(confirmed)))
            self.db.commit()
            self._sync_memory_file()
            return cur.lastrowid

    def memories(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM memories ORDER BY id DESC LIMIT 100")]

    def forget(self, memory_id):
        with self.lock:
            self.db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            self.db.commit()
            self._sync_memory_file()

    def clear_memories(self):
        with self.lock:
            self.db.execute("DELETE FROM memories")
            self.db.commit()
            self._sync_memory_file()

    def proposal(self, entity_id, title, detail, payload):
        with self.lock:
            row = self.db.execute("SELECT id FROM proposals WHERE entity_id=? AND status IN ('pending','approved')",
                                  (entity_id,)).fetchone()
            if row:
                return row[0]
            cur = self.db.execute("INSERT INTO proposals(ts,entity_id,title,detail,payload) VALUES (?,?,?,?,?)",
                                  (time.time(), entity_id, title, detail, json.dumps(payload)))
            self.db.commit()
            return cur.lastrowid

    def proposals(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM proposals ORDER BY id DESC LIMIT 100")]

    def proposal_status(self, proposal_id, status):
        if status not in ("approved", "rejected", "disabled"):
            raise ValueError("status inválido")
        with self.lock:
            row = self.db.execute("SELECT status FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if not row or not ((row[0] == "pending" and status in ("approved", "rejected"))
                           or (row[0] == "approved" and status == "disabled")):
                raise ValueError("Transição de proposta inválida")
            self.db.execute("UPDATE proposals SET status=? WHERE id=?", (status, proposal_id))
            self.db.commit()
