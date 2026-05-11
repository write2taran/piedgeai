#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8080}"

curl -s "${BASE_URL}/health" | python3 -m json.tool
curl -s "${BASE_URL}/chat" \
  -H 'Content-Type: application/json' \
  -d '{"task":"code","prompt":"Write a tiny Python function that reads CPU temperature on Raspberry Pi."}' \
  | python3 -m json.tool
curl -s "${BASE_URL}/status" | python3 -m json.tool
