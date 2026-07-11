<!--
library: anthropic
versions-covered: "anthropic Python SDK 0.x (Messages API, 2026 model line)"
last-verified: 2026-07-11
provenance: auto-generated (pending review)
sources:
  - https://platform.claude.com/docs/en/about-claude/models/overview.md
  - https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking.md
  - https://platform.claude.com/docs/en/build-with-claude/prompt-caching.md
  - https://github.com/anthropics/anthropic-sdk-python
-->

# Anthropic SDK (Python) conventions

Granular guidance for calling Claude via the official `anthropic` Python SDK. Read after detecting `anthropic` / `AsyncAnthropic`. Subordinate to the project's existing conventions — when they conflict, the project wins. The API drifts; ground version-sensitive claims in current docs rather than recalling.

## Contents
- Version check (do this first)
- Client init & auth
- Sync vs async
- Messages request essentials
- Model IDs (2026 line)
- Thinking & effort (this changed — read it)
- Streaming (default for long output)
- Tool use
- System prompts & structured output
- Prompt caching
- Errors, retries, timeouts

## Version check (do this first)
Two things drift and will 400 if you recall the old shape:
1. **Thinking config.** On the current models (Opus 4.8/4.7, Sonnet 5, Fable 5) `thinking={"type": "enabled", "budget_tokens": N}` and `temperature`/`top_p`/`top_k` are **rejected with a 400**. Use `thinking={"type": "adaptive"}` and control depth with `output_config={"effort": ...}`. `budget_tokens` still works only on pre-4.7 models.
2. **Model IDs are bare, undated.** `claude-opus-4-8`, not `claude-opus-4-8-20260…`. Never append a date suffix to a current alias.

If unsure whether an API exists in the installed SDK, check the current docs / SDK repo — do not infer method names from another version.

## Client init & auth
```python
import anthropic
client = anthropic.Anthropic()            # resolves ANTHROPIC_API_KEY (or an `ant auth login` profile)
```
- Prefer the zero-arg constructor; let the key come from env/config (`pydantic-settings`). Never hardcode or log the key.
- Do **not** ask the user for a key when `ANTHROPIC_API_KEY` is unset — the SDK also resolves `ANTHROPIC_AUTH_TOKEN` and on-disk OAuth profiles.
- For a third-party platform, use its dedicated client class (`AnthropicBedrockMantle`, `AnthropicVertex`, `AnthropicAWS`) — not `Anthropic(base_url=...)`.

## Sync vs async
Match the surrounding app. In a FastAPI/`asyncio` service use `AsyncAnthropic` so the request path stays non-blocking:
```python
client = anthropic.AsyncAnthropic()
resp = await client.messages.create(...)
```
For high-concurrency async, install `anthropic[aiohttp]` and pass `http_client=DefaultAioHttpClient()`. Never call the sync client from inside an event loop.

## Messages request essentials
Everything goes through `messages.create` (or `.stream` / `.parse`):
```python
resp = client.messages.create(
    model="claude-opus-4-8",
    max_tokens=16000,
    system="You are …",                     # top-level, not a message
    messages=[{"role": "user", "content": "…"}],
)
# resp.content is a LIST of blocks — check .type before reading .text
text = next((b.text for b in resp.content if b.type == "text"), "")
```
- `messages` is stateless — resend the full history each turn; first message must be `user`; roles alternate (consecutive same-role is merged).
- **`max_tokens` sizing:** default ~16000 non-streaming (keeps under the SDK's ~10-min timeout), ~64000 when streaming. Don't lowball — hitting the cap truncates mid-output (`stop_reason == "max_tokens"`).
- Always branch on `resp.stop_reason` (`end_turn`, `tool_use`, `max_tokens`, `pause_turn`, `refusal`) before assuming `content[0]` is text.

## Model IDs (2026 line)
Use the exact bare alias; default to Opus unless the project chose otherwise.

| Model | ID | Notes |
|---|---|---|
| Claude Opus 4.8 | `claude-opus-4-8` | Default. Most capable Opus; 1M context, 128K output |
| Claude Sonnet 5 | `claude-sonnet-5` | High-volume / cost-sensitive |
| Claude Haiku 4.5 | `claude-haiku-4-5` | Fast, cheap, simple tasks; 200K context |
| Claude Fable 5 | `claude-fable-5` | Only when explicitly requested; different API behavior (thinking always on) |

For live capability/context-window/pricing lookups, query the Models API (`client.models.retrieve(id)`) rather than hardcoding — the `capabilities` field is a nested dict.

## Thinking & effort (this changed — read it)
On Opus 4.8/4.7 and Sonnet 5, thinking is **off** when the field is omitted — set it explicitly:
```python
resp = client.messages.create(
    model="claude-opus-4-8",
    max_tokens=16000,
    thinking={"type": "adaptive", "display": "summarized"},  # display default is "omitted" (empty thinking text)
    output_config={"effort": "high"},                        # low | medium | high | xhigh | max
    messages=[...],
)
```
- `effort` lives **inside `output_config`**, not top-level. Default is `high`; use `xhigh` for hard coding/agentic work, `low` for cheap subtasks.
- `budget_tokens` is gone on these models — don't reintroduce it. There's no 1:1 mapping; pick an `effort` level.
- If you surface reasoning in a UI, set `display: "summarized"` or the blocks stream with empty text (looks like a long pause).

## Streaming (default for long output)
Stream anything with large or open-ended output (`max_tokens` above ~16K raises a `ValueError` non-streaming):
```python
async with client.messages.stream(model="claude-opus-4-8", max_tokens=64000, messages=[...]) as stream:
    async for text in stream.text_stream:
        ...                                  # incremental tokens
    final = await stream.get_final_message() # full Message with usage/stop_reason
```
Prefer `messages.stream()` + `get_final_message()` over `stream=True` — it accumulates state and gives timeout protection even when you don't need per-event handling.

## Tool use
Prefer the SDK **tool runner** over a hand-written loop for custom-tool agents:
```python
from anthropic import beta_tool

@beta_tool
def get_weather(location: str) -> str:
    """Get weather. Args: location: city name."""
    return "…"

runner = client.beta.messages.tool_runner(
    model="claude-opus-4-8", max_tokens=16000,
    tools=[get_weather],
    messages=[{"role": "user", "content": "weather in Paris?"}],
)
for message in runner:                       # loop ends when Claude stops calling tools
    ...
```
Manual loop essentials when you need full control: loop while `stop_reason == "tool_use"`; append the full `response.content` (preserving `tool_use` blocks); return each result as `{"type": "tool_result", "tool_use_id": <id>, "content": ...}` (set `"is_error": True` on failure); return **all** results from one turn in a single `user` message. Always `json.loads()`/inspect `block.input` — never raw-string-match the serialized tool input.

## System prompts & structured output
- Pass instructions via the top-level `system` parameter, not a message.
- For guaranteed-shape JSON, use `client.messages.parse(..., output_format=PydanticModel)` and read `resp.parsed_output` — validation + retry happen for you. Assistant-turn **prefills are rejected (400)** on current models; use structured output or a system instruction instead of prefilling `{`.

## Prompt caching
Caching is a **prefix match** — any byte change in the prefix invalidates everything after it. Render order is `tools` → `system` → `messages`.
- Simplest: top-level `cache_control={"type": "ephemeral"}` auto-caches the last cacheable block.
- Keep the system prompt frozen — never interpolate `datetime.now()`, UUIDs, or per-request IDs into it; put volatile content after the last breakpoint.
- Verify with `resp.usage.cache_read_input_tokens` — zero across identical-prefix requests means a silent invalidator (unsorted `json.dumps`, a varying tool set, a timestamp in `system`).

## Errors, retries, timeouts
- Catch typed exceptions most-specific-first, not one broad class: `anthropic.NotFoundError` (404, bad model ID) → `RateLimitError` (429; read `retry-after`) → `APIStatusError` (other non-2xx) → `APIConnectionError` (network).
- The SDK auto-retries 408/409/429/≥500 + connection errors with backoff (default `max_retries=2`). Configure via `Anthropic(max_retries=…)` or `client.with_options(...)`; only hand-roll retries for behavior beyond that.
- Default request timeout is 10 min; override per-client or per-call (`client.with_options(timeout=30.0)`). Timeouts are retried, so wall-clock can reach `timeout × (max_retries+1)`.
