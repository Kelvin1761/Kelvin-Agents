"""Loopback-only review server with byte-range playback and revision-checked edits."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, urlparse

from .common import load, lock, project_analysis, save, validate_selection
from .captions import document, validate as validate_captions


def serve(project, port=8765):
    project = Path(project).resolve()
    manifest, analysis = project_analysis(project)
    token = secrets.token_urlsafe(24)
    source = Path(manifest["source"]["path"])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Avoid logging the access token.

        def respond(self, data, status=200, mime="application/json"):
            raw = json.dumps(data, ensure_ascii=False).encode() if mime == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            provided = parse_qs(urlparse(self.path).query).get("token", [""])[0]
            if not secrets.compare_digest(provided, token):
                self.respond({"error": "Invalid review token"}, 403)
                return False
            return True

        def do_GET(self):
            if not self.authorized():
                return
            route = urlparse(self.path).path
            if route == "/":
                self.respond(Path(__file__).with_name("review.html").read_bytes(), mime="text/html; charset=utf-8")
            elif route == "/api":
                active_manifest, current = project_analysis(project)
                self.respond(dict(source=source.name, duration=manifest["media"]["duration"],
                                  selection=load(project / "selection.json"),
                                  rows=current["rows"], speech=current["speech"],
                                  captions=document(project, active_manifest, current)))
            elif route == "/video":
                self.video()
            else:
                self.respond({"error": "Not found"}, 404)

        def video(self):
            size = source.stat().st_size
            start, end = 0, size - 1
            request = self.headers.get("Range")
            if request:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", request)
                if not match or not any(match.groups()):
                    self.respond({"error": "Invalid range"}, 416)
                    return
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = min(int(right), size - 1) if right else size - 1
                else:
                    start = max(0, size - int(right))
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            self.send_response(206 if request else 200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if request:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with source.open("rb") as stream:
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = stream.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Seeking cancels the previous byte-range request.

        def do_POST(self):
            if not self.authorized():
                return
            route = urlparse(self.path).path
            if route not in ("/selection", "/captions"):
                self.respond({"error": "Not found"}, 404)
                return
            # Token + loopback binding protect edits from unrelated web pages.
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError("Invalid payload size")
                submitted = json.loads(self.rfile.read(length))
                if route == "/captions":
                    validate_captions(submitted, manifest["media"]["duration"])
                else:
                    validate_selection(submitted, manifest["media"]["duration"])
                with lock(project):
                    if route == "/captions":
                        active_manifest, active_analysis = project_analysis(project)
                        current = document(project, active_manifest, active_analysis)
                        if (submitted.get("revision") != current["revision"] or
                                submitted.get("analysis_file") != active_manifest["analysis_file"]):
                            self.respond({"error": "Captions/recognition changed; reload before saving"}, 409)
                            return
                        save(project / "history" / f"captions-{current['revision']:06}.json", current)
                        submitted["revision"] += 1
                        save(project / "captions.json", submitted)
                        self.respond(submitted)
                        return
                    current = load(project / "selection.json")
                    if submitted.get("revision") != current["revision"]:
                        self.respond({"error": "Selection changed; reload before saving"}, 409)
                        return
                    save(project / "history" / f"selection-{current['revision']:06}.json", current)
                    submitted["revision"] += 1
                    submitted["reviewed"] = True
                    submitted["selected_seconds"] = sum(c["end"] - c["start"] for c in submitted["highlights"])
                    save(project / "selection.json", submitted)
                self.respond(submitted)
            except (ValueError, KeyError, TypeError, RuntimeError) as error:
                self.respond({"error": str(error)}, 400)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Review: http://127.0.0.1:{server.server_port}/?token={token}", flush=True)
    print("Save edits in the browser, then run render. Ctrl-C stops review.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
