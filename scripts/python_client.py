#!/usr/bin/env python3
"""Tiny dependency-free client for the Pi Edge AI runtime."""

from __future__ import annotations

import json
from urllib import request

BASE_URL = "http://127.0.0.1:8080"

payload = {
    "task": "general",
    "prompt": "Give me a stable deployment checklist for a Raspberry Pi LLM service.",
}
req = request.Request(
    f"{BASE_URL}/chat",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with request.urlopen(req, timeout=240) as response:
    print(json.dumps(json.loads(response.read()), indent=2))
