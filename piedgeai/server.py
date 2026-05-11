"""Minimal REST API for the Raspberry Pi edge AI scheduler."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import queue
import threading
import time
from typing import Any
from urllib.parse import urlparse

from .config import RuntimeConfig, load_config
from .model_manager import ModelManager
from .router import TaskRouter
from .sessions import SessionStore


class RuntimeState:
    """Shared single-worker runtime state."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.manager = ModelManager(config.server, config.models)
        self.router = TaskRouter(set(config.models))
        self.sessions = SessionStore(config.server.session_db)
        self.lock = threading.Lock()
        self.jobs: queue.Queue[tuple[dict[str, Any], queue.Queue[dict[str, Any]]]] = queue.Queue(maxsize=4)
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.reaper = threading.Thread(target=self._idle_reaper_loop, daemon=True)
        self.worker.start()
        self.reaper.start()

    def enqueue_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Queue a request so only one inference executes at a time."""

        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self.jobs.put((payload, response_queue), timeout=5)
        try:
            return response_queue.get(timeout=self.config.server.request_timeout_seconds + 30)
        except queue.Empty as exc:
            raise TimeoutError("inference request timed out") from exc

    def _idle_reaper_loop(self) -> None:
        while True:
            self.manager.unload_if_idle()
            time.sleep(5)

    def _worker_loop(self) -> None:
        while True:
            payload, response_queue = self.jobs.get()
            try:
                response_queue.put(self._handle_chat(payload))
            except Exception as exc:  # noqa: BLE001 - API should serialize runtime failures.
                response_queue.put({"error": str(exc)})
            finally:
                self.manager.unload_if_idle()
                self.jobs.task_done()

    def _handle_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("prompt", "")).strip()
        if not prompt:
            return {"error": "prompt is required"}
        session_id = self.sessions.ensure_session(payload.get("session_id"))
        route = self.router.route(prompt, payload.get("task"))
        context = self.sessions.as_prompt_context(session_id)
        full_prompt = f"{context}user: {prompt}\nassistant:"
        with self.lock:
            result = self.manager.infer(route.model_key, full_prompt, payload.get("options"))
            self.manager.record_benchmark(result)
        self.sessions.append(session_id, "user", prompt)
        self.sessions.append(session_id, "assistant", result.text)
        return {
            "session_id": session_id,
            "model": route.model_key,
            "route_reason": route.reason,
            "response": result.text,
            "elapsed_seconds": round(result.elapsed_seconds, 3),
            "prompt_tokens": result.prompt_tokens,
            "predicted_tokens": result.predicted_tokens,
        }


def make_handler(state: RuntimeState) -> type[BaseHTTPRequestHandler]:
    """Create a request handler bound to runtime state."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "piedgeai/0.1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib method name.
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send({"ok": True, "queue_depth": state.jobs.qsize()})
            elif parsed.path == "/status":
                self._send(state.manager.status() | {"queue_depth": state.jobs.qsize()})
            elif parsed.path.startswith("/sessions/"):
                session_id = parsed.path.rsplit("/", 1)[-1]
                self._send(state.sessions.export_session(session_id))
            else:
                self._send({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802 - stdlib method name.
            parsed = urlparse(self.path)
            if parsed.path == "/chat":
                payload = self._read_json()
                try:
                    response = state.enqueue_chat(payload)
                except queue.Full:
                    self._send({"error": "request queue is full"}, HTTPStatus.TOO_MANY_REQUESTS)
                    return
                status = HTTPStatus.BAD_REQUEST if "error" in response else HTTPStatus.OK
                self._send(response, status)
            elif parsed.path == "/unload":
                state.manager.unload()
                self._send({"ok": True})
            else:
                self._send({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            body = self.rfile.read(length).decode("utf-8")
            return json.loads(body)

        def _send(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def run(config_path: str) -> None:
    """Run the LAN-accessible API server."""

    config = load_config(config_path)
    state = RuntimeState(config)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer((config.server.host, config.server.port), handler)
    try:
        httpd.serve_forever()
    finally:
        state.manager.unload()


def main() -> None:
    parser = argparse.ArgumentParser(description="Raspberry Pi edge AI runtime scheduler")
    parser.add_argument("--config", default="configs/models.example.json")
    args = parser.parse_args()
    run(args.config)


if __name__ == "__main__":
    main()
