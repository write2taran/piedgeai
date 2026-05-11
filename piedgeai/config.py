"""Configuration loading for the edge runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelConfig:
    """Runtime settings for one local GGUF model."""

    key: str
    name: str
    path: str
    role: str = ""
    llama_args: list[str] = field(default_factory=list)
    defaults: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ServerConfig:
    """Top-level API and llama.cpp process settings."""

    host: str = "0.0.0.0"
    port: int = 8080
    llama_host: str = "127.0.0.1"
    llama_port: int = 8088
    llama_binary: str = "~/llama.cpp/build/bin/llama-cli"
    idle_unload_seconds: int = 120
    request_timeout_seconds: int = 180
    session_db: str = "sessions.sqlite3"
    benchmark_log: str = "benchmarks.jsonl"


@dataclass(frozen=True)
class RuntimeConfig:
    """Complete runtime configuration."""

    server: ServerConfig
    models: dict[str, ModelConfig]


def load_config(path: str | Path) -> RuntimeConfig:
    """Load a JSON runtime configuration file."""

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    server = ServerConfig(**raw.get("server", {}))
    models = {
        key: ModelConfig(key=key, **value)
        for key, value in raw.get("models", {}).items()
    }
    if not models:
        raise ValueError("configuration must define at least one model")
    return RuntimeConfig(server=server, models=models)
