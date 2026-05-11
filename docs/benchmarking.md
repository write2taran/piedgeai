# Benchmarking methodology

This project treats edge inference quality as an operational stability problem rather than a raw token/sec contest.

## Metrics to collect

For each model and quantization, collect:

- cold load time
- first-token latency, if available from backend logs
- total elapsed request time
- predicted tokens and prompt tokens
- CPU temperature before and after inference
- `MemAvailable`, `SwapFree`, and model RSS
- restart count and failed request count
- qualitative output usefulness at low entropy

## Recommended run matrix

Use short, repeatable prompts that reflect real tasks:

1. General assistant: deployment checklist and concise explanations.
2. Code: small Python/Bash generation, traceback explanation, config edits.
3. Utility: summarize logs, classify intent, extract fields.

Run each prompt at least five times after a fresh boot and again after a long idle period. Compare sustained behavior, not only best-case output.

## Pass/fail guidance for Raspberry Pi 3B+

A model is operationally acceptable when it:

- loads without forcing persistent swap storms
- completes repeated prompts without process death
- leaves enough memory for SSH and the API server
- avoids thermal throttling during sustained use
- produces useful low-temperature responses

A model should be rejected or moved to an experimental profile when it requires large context settings, destabilizes SSH responsiveness, or leaves the board in a degraded swap-heavy state after inference.
