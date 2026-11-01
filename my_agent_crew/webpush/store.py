"""The server's push key and the browsers that asked to be told, kept in the home.

One small JSON file (`webpush.json`) rather than a table: a handful of devices, read on
every push and written only when one subscribes or goes away. The key is made the first
time it is asked for and kept for good, since every subscription was made against it; a
new key would silently orphan them all."""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec

from my_agent_crew.store.stamps import now_iso
from my_agent_crew.webpush import crypto

logger = logging.getLogger(__name__)
FILE_NAME = "webpush.json"
# More than a person's devices; enough that a page subscribing in a loop cannot grow it.
MAX_SUBSCRIPTIONS = 20


@dataclass(frozen=True)
class Subscription:
    endpoint: str
    p256dh: str
    auth: str
    # How the push service reaches whoever runs this server: the page's https origin when
    # it had one (`vapid_header`).
    subject: str
    added_at: str = ""


class PushStore:
    def __init__(self, home: Path):
        self._path = home / FILE_NAME
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            logger.warning("webpush: %s is unreadable; starting over", FILE_NAME)
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self._path)

    def key(self) -> ec.EllipticCurvePrivateKey:
        with self._lock:
            data = self._read()
            raw = data.get("key")
            if isinstance(raw, str):
                return crypto.private_from(raw)
            key = crypto.new_key()
            data["key"] = crypto.private_raw(key)
            self._write(data)
            return key

    def public_key(self) -> str:
        return crypto.public_raw(self.key())

    def subscriptions(self) -> list[Subscription]:
        with self._lock:
            rows = self._read().get("subscriptions", [])
        found = []
        for row in rows if isinstance(rows, list) else []:
            try:
                found.append(Subscription(**row))
            except TypeError:
                continue
        return found

    def add(self, sub: Subscription) -> None:
        """Keeps one row per endpoint, the newest keys winning; the oldest go past the cap."""
        with self._lock:
            data = self._read()
            rows = [r for r in data.get("subscriptions", []) if r.get("endpoint") != sub.endpoint]
            rows.append(asdict(sub) | {"added_at": sub.added_at or now_iso()})
            data["subscriptions"] = rows[-MAX_SUBSCRIPTIONS:]
            self._write(data)

    def remove(self, endpoint: str) -> bool:
        with self._lock:
            data = self._read()
            rows = data.get("subscriptions", [])
            kept = [r for r in rows if r.get("endpoint") != endpoint]
            if len(kept) == len(rows):
                return False
            data["subscriptions"] = kept
            self._write(data)
            return True
