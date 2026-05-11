# Pi Edge AI Runtime Scheduler

A lightweight Raspberry Pi edge AI runtime that matches a simple existing `llama.cpp` setup: **run one `llama-cli` process for one request, capture the answer, then let the process exit so RAM is reclaimed**.

This project is intentionally not Docker, not Kubernetes, not LangChain, and not a generic chatbot demo. It is a small LAN REST wrapper for constrained local inference on a Raspberry Pi 3B+.

## What changed for Raspberry Pi compatibility

The runtime now defaults to the binary many Pi users already have after compiling `llama.cpp`:

```text
/home/pi/llama.cpp/build/bin/llama-cli
```

The example model path also matches a common local llama.cpp layout:

```text
/home/pi/llama.cpp/models/qwen1_5b.gguf
```

So your old command:

```bash
./build/bin/llama-cli -m models/qwen1_5b.gguf -c 64 --temp 0.4 --top-p 0.8
```

maps directly to this runtime config:

```json
"llama_binary": "/home/pi/llama.cpp/build/bin/llama-cli",
"path": "/home/pi/llama.cpp/models/qwen1_5b.gguf",
"llama_args": ["-c", "64", "--threads", "3", "--batch-size", "32"],
"defaults": {"temperature": 0.4, "top_p": 0.8, "max_tokens": 128}
```

## Runtime architecture

```text
LAN client
  -> piedgeai REST API
  -> single worker queue
  -> simple deterministic router
  -> one llama-cli subprocess
  -> SQLite session store
  -> JSONL benchmark log
```

Important behavior:

- Only one inference request runs at a time.
- No resident `llama-server` daemon is required.
- No model is kept warm in RAM between requests.
- Each request starts `llama-cli`, runs completion, captures stdout, and exits.
- `/unload` can terminate a running `llama-cli` process if needed.
- Sessions are stored outside the model in SQLite.

## 1. Build llama.cpp on the Raspberry Pi

If you already have `~/llama.cpp/build/bin/llama-cli`, you can skip to section 2.

From the Pi:

```bash
cd ~
sudo apt update
sudo apt install -y git cmake build-essential curl python3 python3-venv python3-pip
```

Download llama.cpp if needed:

```bash
cd ~
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
```

Or with `wget` if you do not want to use git:

```bash
cd ~
wget -O llama.cpp.tar.gz https://github.com/ggerganov/llama.cpp/archive/refs/heads/master.tar.gz
tar -xzf llama.cpp.tar.gz
mv llama.cpp-master llama.cpp
cd llama.cpp
```

Build on the Pi 3B+ with a low parallel job count:

```bash
cmake -B build -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j2
```

Confirm the binary exists:

```bash
./build/bin/llama-cli --help | head
```

## 2. Put your GGUF model where the config expects it

The default config expects this file:

```text
/home/pi/llama.cpp/models/qwen1_5b.gguf
```

Check your model files:

```bash
find ~/llama.cpp/models -type f -name '*.gguf' -print
```

If your file has a different name, edit `configs/models.example.json` and change the `path` value.

## 3. Test llama-cli directly first

Run the same style of command you already used:

```bash
cd ~/llama.cpp
./build/bin/llama-cli -m models/qwen1_5b.gguf -c 64 --temp 0.4 --top-p 0.8 -p "Say hello in one short sentence." -n 64
```

If this works, the runtime can use the same binary and model path.

## 4. Install and run this runtime

Clone or copy this repository onto the Pi, then:

```bash
cd ~/piedgeai
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Run the API:

```bash
piedgeai --config configs/models.example.json
```

The API binds to `0.0.0.0:8080`, so it is reachable from another computer on your LAN.

## 5. Test the API

From the Pi:

```bash
curl http://127.0.0.1:8080/health
```

From your laptop:

```bash
curl http://PI_IP_ADDRESS:8080/health
```

Send a prompt:

```bash
curl -s http://PI_IP_ADDRESS:8080/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Say hello in one short sentence."}' \
  | python3 -m json.tool
```

Force a model key if you add more models later:

```bash
curl -s http://PI_IP_ADDRESS:8080/chat \
  -H 'Content-Type: application/json' \
  -d '{"task":"general","prompt":"Write a tiny Bash command to show CPU temperature."}' \
  | python3 -m json.tool
```

Manual unload while a request is running:

```bash
curl -X POST http://PI_IP_ADDRESS:8080/unload
```

Check process and system telemetry:

```bash
curl -s http://PI_IP_ADDRESS:8080/status | python3 -m json.tool
```

## 6. Configuration reference

The default config is intentionally small:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8080,
    "llama_binary": "/home/pi/llama.cpp/build/bin/llama-cli",
    "idle_unload_seconds": 5,
    "request_timeout_seconds": 180,
    "session_db": "sessions.sqlite3",
    "benchmark_log": "benchmarks.jsonl"
  },
  "models": {
    "general": {
      "name": "Qwen 1.5B local model",
      "path": "/home/pi/llama.cpp/models/qwen1_5b.gguf",
      "llama_args": ["-c", "64", "--threads", "3", "--batch-size", "32"],
      "defaults": {"temperature": 0.4, "top_p": 0.8, "max_tokens": 128}
    }
  }
}
```

Field meanings:

| Field | Meaning |
| --- | --- |
| `llama_binary` | Full path to your compiled `llama-cli`. |
| `path` | Full path to the GGUF model file. |
| `llama_args` | Raw llama.cpp CLI args such as `-c 64`, threads, and batch size. |
| `temperature` | Maps to `--temp`. |
| `top_p` | Maps to `--top-p`. |
| `max_tokens` | Maps to `-n`. |
| `request_timeout_seconds` | Kills a stuck CLI process after this many seconds. |

## 7. Add more models later

Start with one known-good model. After that works, add more keys under `models`:

```json
"code": {
  "name": "Qwen coder small",
  "path": "/home/pi/llama.cpp/models/qwen-coder.gguf",
  "role": "code help",
  "llama_args": ["-c", "128", "--threads", "3", "--batch-size", "32"],
  "defaults": {"temperature": 0.1, "top_p": 0.75, "max_tokens": 128}
}
```

Then call it with:

```bash
curl -s http://PI_IP_ADDRESS:8080/chat \
  -H 'Content-Type: application/json' \
  -d '{"task":"code","prompt":"Debug this Python traceback."}' \
  | python3 -m json.tool
```

## 8. Pi 3B+ stability notes

Recommended first settings:

- `-c 64` or `-c 128`
- `--threads 3`
- `--batch-size 32`
- `max_tokens` between `64` and `128`
- `temperature` between `0.1` and `0.4`

If the Pi swaps heavily, reduce context size first, then max tokens, then model size.

## 9. Logs and session files

The runtime writes:

- `sessions.sqlite3` for lightweight external conversation history
- `benchmarks.jsonl` for elapsed time, selected model, temperature, and memory counters

Inspect benchmark output:

```bash
tail -n 20 benchmarks.jsonl
```

## 10. Repository layout

```text
piedgeai/
  config.py          JSON configuration loader
  model_manager.py   one-request llama-cli subprocess lifecycle
  monitoring.py      /proc and thermal telemetry helpers
  router.py          deterministic task routing rules
  server.py          dependency-free REST API and single-worker queue
  sessions.py        SQLite-backed external session storage
configs/
  models.example.json
tests/
```
