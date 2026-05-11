"""Run one llama.cpp CLI process per request and then reclaim RAM."""

from __future__ import annotations

import json
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ModelConfig, ServerConfig
from .monitoring import process_rss_kb, read_memory_kb, read_temperature_c


@dataclass
class InferenceResult:
    """Result metadata from one llama.cpp CLI run."""

    text: str
    model_key: str
    elapsed_seconds: float
    prompt_tokens: int | None = None
    predicted_tokens: int | None = None


class ModelManager:
    """Run exactly one llama-cli subprocess at a time.

    This intentionally uses the binary Raspberry Pi users commonly already have
    after building llama.cpp: ``~/llama.cpp/build/bin/llama-cli``.  A request
    starts that process, waits for completion, then clears the process handle so
    the OS can reclaim model RAM.  No llama-server daemon is required.
    """

    def __init__(self, server: ServerConfig, models: dict[str, ModelConfig]) -> None:
        self.server = server
        self.models = models
        self.active_key: str | None = None
        self.process: subprocess.Popen[str] | None = None
        self.last_used = 0.0

    def unload(self) -> None:
        """Terminate the active llama-cli process if a request is running."""

        if not self.process:
            self.active_key = None
            return
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        self.active_key = None

    def unload_if_idle(self) -> bool:
        """Compatibility hook for the API idle reaper.

        llama-cli exits after every request, so there is normally nothing to
        reap. If a process somehow remains after the idle limit, terminate it.
        """

        if not self.process or self.process.poll() is not None:
            self.process = None
            self.active_key = None
            return False
        idle_for = time.time() - self.last_used if self.last_used else 0
        if idle_for >= self.server.idle_unload_seconds:
            self.unload()
            return True
        return False

    def infer(self, model_key: str, prompt: str, options: dict[str, Any] | None = None) -> InferenceResult:
        """Run the selected model with llama-cli and return captured output."""

        if model_key not in self.models:
            raise KeyError(f"unknown model: {model_key}")

        self.unload()
        model = self.models[model_key]
        command = self._build_command(model, prompt, options or {})
        started = time.monotonic()
        self.active_key = model_key
        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as exc:
            self.active_key = None
            self.process = None
            raise RuntimeError(f"could not start llama-cli: {command[0]}") from exc

        try:
            stdout, stderr = self.process.communicate(timeout=self.server.request_timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            self.unload()
            raise TimeoutError(f"llama-cli timed out after {self.server.request_timeout_seconds}s") from exc
        finally:
            elapsed = time.monotonic() - started
            self.last_used = time.time()

        return_code = self.process.returncode if self.process else None
        self.process = None
        self.active_key = None
        if return_code != 0:
            detail = stderr.strip() or stdout.strip() or f"exit code {return_code}"
            raise RuntimeError(f"llama-cli failed: {detail}")

        return InferenceResult(
            text=self._clean_output(stdout, prompt),
            model_key=model_key,
            elapsed_seconds=elapsed,
            predicted_tokens=self._option_int({**model.defaults, **(options or {})}, "max_tokens"),
        )

    def status(self) -> dict[str, Any]:
        """Return lightweight process and host telemetry."""

        pid = self.process.pid if self.process and self.process.poll() is None else None
        return {
            "active_model": self.active_key if pid else None,
            "pid": pid,
            "llama_rss_kb": process_rss_kb(pid),
            "temperature_c": read_temperature_c(),
            "memory_kb": read_memory_kb(),
            "idle_seconds": round(time.time() - self.last_used, 3) if self.last_used else None,
        }

    def record_benchmark(self, result: InferenceResult) -> None:
        """Append a compact JSONL benchmark record."""

        record = {
            "ts": time.time(),
            "model": result.model_key,
            "elapsed_seconds": result.elapsed_seconds,
            "prompt_tokens": result.prompt_tokens,
            "predicted_tokens": result.predicted_tokens,
            "temperature_c": read_temperature_c(),
            "memory_kb": read_memory_kb(),
        }
        path = Path(self.server.benchmark_log)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    def _build_command(self, model: ModelConfig, prompt: str, options: dict[str, Any]) -> list[str]:
        merged = {**model.defaults, **options}
        command = [
            self._expand_path(self.server.llama_binary),
            "-m",
            self._expand_path(model.path),
            "-p",
            prompt,
            *model.llama_args,
        ]
        max_tokens = self._option_int(merged, "max_tokens")
        if max_tokens is not None:
            command.extend(["-n", str(max_tokens)])
        if "temperature" in merged:
            command.extend(["--temp", str(merged["temperature"])])
        if "top_p" in merged:
            command.extend(["--top-p", str(merged["top_p"])])
        if "seed" in merged:
            command.extend(["--seed", str(merged["seed"])])
        return command

    @staticmethod
    def _expand_path(value: str) -> str:
        return str(Path(value).expanduser()) if value.startswith(("~", ".")) else value

    @staticmethod
    def _option_int(options: dict[str, Any], key: str) -> int | None:
        value = options.get(key)
        return int(value) if value is not None else None

    @staticmethod
    def _clean_output(stdout: str, prompt: str) -> str:
        text = stdout.strip()
        prompt = prompt.strip()
        if prompt and text.startswith(prompt):
            text = text[len(prompt) :].strip()
        return text
