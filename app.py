"""Local Glean. Bind to this computer only."""

import json
import mimetypes
import re
import threading
import time
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import glean
import paths
import transcribe

ROOT = paths.resource_dir()
STATIC = ROOT / "static"
OUTPUT = paths.user_dir() / "output"
HOST = "127.0.0.1"
PORT = 8765

JOBS = {}
LOCK = threading.Lock()
MEDIA = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".mp3", ".wav", ".m4a", ".aac", ".ogg"}


def safe_name(name):
    stem = Path(name or "sermon").name
    stem = re.sub(r"[^\w.\- ]+", "", stem).strip() or "sermon"
    return stem[:120]


def write_result(folder, result):
    (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (folder / "glean.md").write_text(glean.to_markdown(result), encoding="utf-8")
    (folder / "transcript.srt").write_text(glean.to_srt(result["transcript"]), encoding="utf-8")


def with_punches(result, folder=None):
    if result.get("punches") or not result.get("transcript"):
        return result
    result["punches"] = glean.find_punches(result["transcript"])
    if folder:
        write_result(folder, result)
    return result


def run_job(job_id, source, accuracy):
    job = JOBS[job_id]
    folder = OUTPUT / job_id

    def status(message):
        job["message"] = message

    try:
        suffix = source.suffix.lower()
        if suffix in MEDIA:
            segments = transcribe.transcribe(source, accuracy, status)
            source.unlink(missing_ok=True)
        else:
            status("Reading the transcript.")
            segments = glean.parse_transcript(source.read_text(encoding="utf-8", errors="replace"))
        if not segments:
            raise RuntimeError("No words were found in that file.")
        status("Keeping the grain.")
        title = source.stem if source.exists() else job["title"]
        result = glean.glean(segments, title)
        result["id"] = job_id
        result["created"] = time.time()
        write_result(folder, result)
        job["result"] = result
        job["state"] = "done"
        job["message"] = "Ready."
    except Exception as error:
        job["state"] = "error"
        job["message"] = str(error)
        traceback.print_exc()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[glean] {self.address_string()} {fmt % args}")

    def _send(self, code, body, content_type):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload), "application/json; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/index.html"):
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/library":
            self._json(200, {"items": library()})
            return
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "api" and parts[1] == "jobs":
            job_id = parts[2]
            folder = OUTPUT / job_id
            if len(parts) == 3:
                with LOCK:
                    job = JOBS.get(job_id)
                if job:
                    payload = {"state": job["state"], "message": job["message"], "title": job["title"]}
                    if job["state"] == "done":
                        payload["result"] = public_result(with_punches(job["result"], folder))
                    self._json(200, payload)
                    return
                saved = folder / "result.json"
                if saved.exists():
                    result = with_punches(json.loads(saved.read_text(encoding="utf-8")), folder)
                    self._json(200, {"state": "done", "message": "Ready.", "title": result["title"], "result": public_result(result)})
                    return
            if len(parts) == 4 and parts[3] in ("markdown", "srt") and (folder / "result.json").exists():
                result = with_punches(json.loads((folder / "result.json").read_text(encoding="utf-8")), folder)
                if parts[3] == "markdown":
                    self._send(200, glean.to_markdown(result), "text/markdown; charset=utf-8")
                else:
                    self._send(200, glean.to_srt(result["transcript"]), "application/x-subrip; charset=utf-8")
                return
        file_path = STATIC / path.lstrip("/")
        if file_path.is_file():
            mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self._send(200, file_path.read_bytes(), mime)
            return
        self._json(404, {"message": "Not found."})

    def do_POST(self):
        if urlparse(self.path).path != "/api/jobs":
            self._json(404, {"message": "Not found."})
            return
        length = int(self.headers.get("Content-Length", "0"))
        filename = safe_name(self.headers.get("X-Filename", "sermon.txt"))
        accuracy = self.headers.get("X-Accuracy", "high")
        if accuracy not in transcribe.MODELS:
            accuracy = "high"
        job_id = uuid.uuid4().hex[:12]
        folder = OUTPUT / job_id
        folder.mkdir(parents=True, exist_ok=True)
        source = folder / filename
        remaining = length
        with source.open("wb") as handle:
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                handle.write(chunk)
                remaining -= len(chunk)
        title = Path(filename).stem
        with LOCK:
            JOBS[job_id] = {"state": "running", "message": "Starting.", "title": title, "result": None}
        threading.Thread(target=run_job, args=(job_id, source, accuracy), daemon=True).start()
        self._json(200, {"id": job_id})


def public_result(result):
    return result


def library():
    items = []
    if not OUTPUT.exists():
        return items
    for folder in OUTPUT.iterdir():
        saved = folder / "result.json"
        if not saved.is_file():
            continue
        try:
            result = json.loads(saved.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append({
            "id": folder.name,
            "title": result.get("title") or folder.name,
            "wordCount": result.get("wordCount") or 0,
            "duration": result.get("duration") or 0,
            "created": result.get("created") or 0,
        })
    items.sort(key=lambda item: item["created"], reverse=True)
    return items


def start_server():
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        server = ThreadingHTTPServer((HOST, 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Bridge:
    def save_export(self, job_id, kind):
        folder = OUTPUT / str(job_id)
        saved = folder / "result.json"
        if not saved.exists():
            return False
        result = json.loads(saved.read_text(encoding="utf-8"))
        if kind == "srt":
            body = glean.to_srt(result["transcript"])
            suggested = f"{result['title']}.srt"
        else:
            body = glean.to_markdown(result)
            suggested = f"{result['title']}.md"
        import webview
        window = webview.windows[0] if webview.windows else None
        if window is None:
            return False
        chosen = window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=suggested,
        )
        if not chosen:
            return False
        path = Path(chosen[0] if isinstance(chosen, (list, tuple)) else chosen)
        path.write_text(body, encoding="utf-8")
        return True


def open_window(url):
    try:
        import webview
    except ImportError:
        webbrowser.open(url)
        return False
    webview.create_window(
        "Glean",
        url,
        width=1180,
        height=820,
        min_size=(820, 560),
        background_color="#141210",
        text_select=True,
        js_api=Bridge(),
    )
    webview.start(gui="edgechromium")
    return True


def main():
    OUTPUT.mkdir(exist_ok=True)
    server = start_server()
    url = f"http://{HOST}:{server.server_address[1]}"
    print(f"Glean is on this computer at {url}")
    if not open_window(url):
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    server.shutdown()


if __name__ == "__main__":
    main()
