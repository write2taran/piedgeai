# Runtime design

The scheduler is intentionally small because every resident dependency competes with the active model for RAM.

## Request lifecycle

1. A LAN client sends `POST /chat`.
2. The API places the request on a bounded queue.
3. A single worker selects a model with deterministic routing rules.
4. The model manager unloads any currently active model.
5. The target model starts through `llama-server`.
6. Recent SQLite session history is rendered into a compact prompt prefix.
7. The completion response is persisted and benchmark telemetry is appended.
8. Idle reclamation may unload the model after the configured timeout.

## Why subprocess orchestration

Using `llama-server` as a child process provides a simple fault boundary. If a model load fails or RAM pressure kills the backend, the API process can report the failure instead of corrupting in-process state. This is more practical on a 1GB Pi than embedding heavier orchestration frameworks.

## Why no embeddings router

A semantic router would require another resident model or extra inference pass. The current router uses transparent string rules because the project prioritizes predictable memory use and deterministic behavior over sophisticated classification.
