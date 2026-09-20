"""Faux service Gmail (OAuth2 token + users.messages.send) pour le scénario « service externe ».

Le mode se change à chaud, sans redémarrage :
    curl -X POST localhost:19081/_mode -d '{"mode": "http500"}'
    curl localhost:19081/_stats                       # compteurs par mode et messages reçus
    curl -X POST localhost:19081/_reset

Modes : ok | http500 | http429 | invalid (200 non JSON) | slow (attente `delay` s puis 200)
        | hang (ne répond jamais) | down (ferme la connexion sans réponse)
        | ack_lost (le message part, puis la connexion se ferme sans réponse)
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"mode": "ok", "delay": 30.0}
STATS = {"requests": 0, "token": 0, "send_ok": 0, "by_mode": {}, "messages": []}
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # journal compact sur stdout
        print(f"[mock-gmail] {self.command} {self.path} mode={STATE['mode']}", flush=True)

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def do_GET(self):
        if self.path == "/_stats":
            with LOCK:
                self._json(200, {**STATS, "mode": STATE["mode"], "messages": len(STATS["messages"])})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        body = self._body()
        if self.path == "/_mode":
            data = json.loads(body or b"{}")
            STATE["mode"] = data.get("mode", "ok")
            STATE["delay"] = float(data.get("delay", STATE["delay"]))
            self._json(200, STATE)
            return
        if self.path == "/_reset":
            with LOCK:
                STATS.update({"requests": 0, "token": 0, "send_ok": 0, "by_mode": {}, "messages": []})
            STATE.update({"mode": "ok", "delay": 30.0})
            self._json(200, STATE)
            return
        mode = STATE["mode"]
        with LOCK:
            STATS["requests"] += 1
            STATS["by_mode"][mode] = STATS["by_mode"].get(mode, 0) + 1
        if mode == "hang":
            time.sleep(3600)
            return
        if mode == "down":
            self.close_connection = True
            self.connection.close()
            return
        if mode == "slow":
            time.sleep(STATE["delay"])
        if mode == "http500":
            self._json(500, {"error": {"code": 500, "message": "backendError"}})
            return
        if mode == "http429":
            self.send_response(429)
            self.send_header("Retry-After", "30")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if mode == "invalid":
            payload = b"<html>upstream proxy error</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path.endswith("/token"):
            with LOCK:
                STATS["token"] += 1
            self._json(200, {"access_token": "lab-access-token", "expires_in": 3600})
            return
        if self.path.endswith("/messages/send"):
            if mode == "ack_lost":
                with LOCK:
                    STATS["messages"].append(json.loads(body or b"{}").get("raw", "")[:64])
                self.close_connection = True
                self.connection.close()
                return
            with LOCK:
                STATS["send_ok"] += 1
                STATS["messages"].append(json.loads(body or b"{}").get("raw", "")[:64])
            self._json(200, {"id": f"msg-{STATS['send_ok']}", "labelIds": ["SENT"]})
            return
        self._json(404, {"error": "not found"})


if __name__ == "__main__":
    print("[mock-gmail] écoute sur :8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
