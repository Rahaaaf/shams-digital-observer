import os
import threading
from datetime import datetime

try:
    from flask import Flask, request, jsonify
except Exception:
    Flask = None
    request = None
    jsonify = None


class UiPathBridge:
    def __init__(self, on_event, host="0.0.0.0", port=5055):
        self.on_event = on_event
        self.host = host
        self.port = port
        self.secret = os.environ.get("UIPATH_SECRET", "")
        self.available = Flask is not None

        if not self.available:
            print("[UIPATH] Flask not installed. Bridge disabled.")
            return

        self.app = Flask(__name__)
        self.setup_routes()

    def setup_routes(self):
        @self.app.get("/")
        def index():
            return jsonify({
                "ok": True,
                "name": "Shams UiPath Bridge",
                "time": datetime.now().isoformat(timespec="seconds"),
            })

        @self.app.post("/event")
        def event():
            if self.secret:
                incoming = request.headers.get("X-Shams-Secret", "")
                if incoming != self.secret:
                    return jsonify({"ok": False, "error": "unauthorized"}), 401

            data = request.get_json(force=True, silent=True) or {}

            event_data = {
                "source": data.get("source", "uipath"),
                "event": data.get("event", "unknown"),
                "message": data.get("message", ""),
                "level": data.get("level", "info"),
                "time": datetime.now().isoformat(timespec="seconds"),
                "raw": data,
            }

            threading.Thread(
                target=self.on_event,
                args=(event_data,),
                daemon=True,
            ).start()

            return jsonify({"ok": True, "received": event_data})

    def start(self):
        if not self.available:
            return

        thread = threading.Thread(
            target=self.app.run,
            kwargs={
                "host": self.host,
                "port": self.port,
                "debug": False,
                "use_reloader": False,
            },
            daemon=True,
        )
        thread.start()
        print(f"[OK] UiPath bridge running on http://{self.host}:{self.port}/event")
