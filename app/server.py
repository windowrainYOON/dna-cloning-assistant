"""Local HTTP server for the DNA cloning assistant.

Standard library only — `python3 run.py` is all it takes to start.
The browser talks to a small JSON API:

    GET  /api/state              current plasmid
    POST /api/open               {path} or {data: base64}  -> load a .dna file
    POST /api/save               {path} -> write the current plasmid back out
    POST /api/sequence/edit      {start, end, replacement}
    POST /api/features           add / update / delete a feature
    POST /api/primers            add / update / delete a primer
    POST /api/pcr                {primers:[{name,sequence}], conditions:{}}
"""

from __future__ import annotations

import base64
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .pcr import design_pcr
from .snapgene import Feature, Primer, SnapGeneFile

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

_lock = threading.Lock()
_state: dict[str, object] = {"file": None, "path": None}


def load(path: str) -> None:
    with _lock:
        _state["file"] = SnapGeneFile.read(path)
        _state["path"] = os.path.abspath(path)


def _current() -> SnapGeneFile:
    f = _state.get("file")
    if f is None:
        raise ValueError("아직 열린 파일이 없습니다. 먼저 .dna 파일을 여세요.")
    return f  # type: ignore[return-value]


def _state_payload() -> dict[str, object]:
    f = _state.get("file")
    if f is None:
        return {"loaded": False}
    data = f.to_dict()  # type: ignore[union-attr]
    data["loaded"] = True
    data["path"] = _state.get("path")
    data["name"] = os.path.basename(str(_state.get("path") or "untitled.dna"))
    return data


class Handler(BaseHTTPRequestHandler):
    server_version = "DNACloningAssistant/1.0"

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        pass

    # ------------------------------------------------------------- helpers

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    # ----------------------------------------------------------------- GET

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self._json(_state_payload())
            return
        if path == "/api/download":
            try:
                f = _current()
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
                return
            name = os.path.basename(str(_state.get("path") or "plasmid.dna"))
            body = f.to_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            self._json({"error": "not found"}, 404)
            return
        ctype = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8",
                 "css": "text/css; charset=utf-8"}.get(rel.rsplit(".", 1)[-1],
                                                       "application/octet-stream")
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype)

    # ---------------------------------------------------------------- POST

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._body()
            with _lock:
                payload = self._dispatch(path, body)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
            return
        except Exception as exc:  # surfaced in the UI rather than the console
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            return
        if payload is None:
            self._json({"error": "not found"}, 404)
            return
        self._json(payload)

    def _dispatch(self, path: str, body: dict):
        if path == "/api/open":
            if body.get("data"):
                raw = base64.b64decode(body["data"])
                _state["file"] = SnapGeneFile.read(raw)
                _state["path"] = body.get("name") or "uploaded.dna"
            else:
                target = os.path.expanduser(body["path"])
                _state["file"] = SnapGeneFile.read(target)
                _state["path"] = os.path.abspath(target)
            return _state_payload()

        if path == "/api/save":
            f = _current()
            target = os.path.expanduser(body.get("path") or str(_state["path"]))
            f.write(target)
            _state["path"] = os.path.abspath(target)
            return {"saved": os.path.abspath(target)}

        if path == "/api/sequence/edit":
            f = _current()
            start, end = int(body["start"]), int(body["end"])
            if not (1 <= start <= end <= len(f.sequence)):
                raise ValueError("편집 범위가 서열 길이를 벗어났습니다.")
            f.apply_edit(start, end, body.get("replacement", ""))
            return _state_payload()

        if path == "/api/features":
            f = _current()
            action = body.get("action")
            if action == "add":
                f.features.append(Feature.from_dict(body["feature"]))
            elif action == "update":
                f.features[int(body["index"])] = Feature.from_dict(body["feature"])
            elif action == "delete":
                del f.features[int(body["index"])]
            else:
                raise ValueError(f"알 수 없는 action: {action}")
            f.features.sort(key=lambda x: (x.start, x.end))
            return _state_payload()

        if path == "/api/primers":
            f = _current()
            action = body.get("action")
            if action == "add":
                f.primers.append(Primer.from_dict(body["primer"]))
            elif action == "update":
                f.primers[int(body["index"])] = Primer.from_dict(body["primer"])
            elif action == "delete":
                del f.primers[int(body["index"])]
            else:
                raise ValueError(f"알 수 없는 action: {action}")
            return _state_payload()

        if path == "/api/pcr":
            f = _state.get("file")
            template = f.sequence if f else None          # type: ignore[union-attr]
            circular = bool(f.is_circular) if f else False  # type: ignore[union-attr]
            if body.get("ignore_template"):
                template, circular = None, False
            return design_pcr(body.get("primers", []), template, circular,
                              body.get("conditions"))
        return None


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"DNA Cloning Assistant → {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()
