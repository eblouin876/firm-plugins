<!--
library: slack-bolt
versions-covered: "1.2x (Bolt for Python), Socket Mode + asyncio"
last-verified: 2026-07-11
provenance: auto-generated (pending review)
sources:
  - https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/
  - https://docs.slack.dev/tools/bolt-python/concepts/async/
  - https://github.com/slackapi/bolt-python/blob/main/examples/socket_mode_async.py
  - https://pypi.org/project/slack-bolt/
-->

# Slack Bolt (Python) conventions

Granular guidance for a Slack app built on `slack-bolt`. Read after detecting `slack-bolt` / `slack_bolt`. Subordinate to the project's existing conventions — when they conflict, the project wins.

## Contents
- Version check (do this first)
- Sync vs async (pick one and stay on it)
- Connection mode: Socket Mode vs HTTP
- Tokens & scopes
- Listeners (events, actions, commands, shortcuts, views)
- The `ack()` discipline
- Listener arguments & responding
- Lazy listeners and long work
- Errors, retries, and idempotency
- Testing

## Version check (do this first)
Confirm the installed **`slack-bolt` major/minor** (currently 1.2x; 1.29.0 is recent, Python 3.8+—3.14). Socket Mode arrived in 1.2.0, so anything ≥1.2 has it. The decisive fork is **sync vs async**: the async app is a *different* import path and every listener must be `async def` with `await`ed calls. If unsure whether a method exists in the installed version, check the current Bolt docs rather than recalling — the SDK moves and adapter modules are reorganized between minors.

## Sync vs async (pick one and stay on it)
Bolt ships two parallel APIs. Choose based on the surrounding app (FastAPI/`asyncio` → async; a plain worker → sync) and never mix them.

| | Sync | Async |
|---|---|---|
| App class | `from slack_bolt import App` | `from slack_bolt.app.async_app import AsyncApp` |
| Socket handler | `slack_bolt.adapter.socket_mode.SocketModeHandler` | `slack_bolt.adapter.socket_mode.async_handler.AsyncSocketModeHandler` |
| Listeners | `def handler(...)` | `async def handler(...)` |
| Calls | `ack()`, `say(...)`, `client.chat_postMessage(...)` | `await ack()`, `await say(...)`, `await client.chat_postMessage(...)` |
| HTTP backend | `slack_sdk` (requests) | `aiohttp` (install it) |

Async is the right default inside a FastAPI/`asyncio` service: the whole request path stays non-blocking and the Socket Mode WebSocket lives on the same event loop. In async, **every** injected utility (`ack`, `say`, `respond`, `client`) is a coroutine — forgetting one `await` is the most common bug, and it fails silently (the coroutine is never scheduled).

## Connection mode: Socket Mode vs HTTP
- **Socket Mode** — the app opens an outbound WebSocket to Slack; no public URL, no request-signature verification, no ngrok. Ideal for internal tools and tailnet-hosted apps. Requires an **app-level token** with `connections:write`.
- **HTTP (Request URL)** — Slack POSTs events to a public endpoint you host; requires the signing secret for request verification and a reachable URL. Use it for public/high-scale apps.

Async Socket Mode startup:
```python
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

app = AsyncApp(token=os.environ["SLACK_BOT_TOKEN"])
# ... register listeners on `app` ...

handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
await handler.start_async()          # blocks, maintaining the socket
# or, when embedding in an existing loop (e.g. a FastAPI lifespan):
await handler.connect_async()        # returns after the socket is up; you own the loop
```
When embedding in a web framework, use `connect_async()` (not `start_async()`) inside the app's lifespan so your own server keeps running — and know that it **retries until Slack accepts the socket**, so the app can't serve traffic until valid tokens connect. Tests must bypass this by attaching a mock handler.

## Tokens & scopes
Three distinct secrets — keep all in env/config (`pydantic-settings`), never in code:
- **Bot token** (`xoxb-…`) → `App(token=...)`. Carries the bot's OAuth scopes (`chat:write`, `app_mentions:read`, `commands`, …). Grant only what the app uses.
- **App-level token** (`xapp-…`, scope `connections:write`) → the Socket Mode handler. Socket Mode only.
- **Signing secret** → `App(signing_secret=...)` for HTTP mode request verification. Not needed in Socket Mode.

## Listeners (events, actions, commands, shortcuts, views)
Register with decorators (or `app.event("…")(fn)` for programmatic registration):
```python
@app.event("app_mention")
async def on_mention(event, say):
    await say(f"Hi <@{event['user']}>")

@app.command("/hello")
async def on_cmd(ack, respond):
    await ack()                         # within 3s — see below
    await respond("working on it…")

@app.action("approve_button")
async def on_action(ack, body, client):
    await ack()
    ...

@app.view("submit_modal")
async def on_submit(ack, view):
    await ack()
    ...
```
- **`@app.event`** — Events API subscriptions (`app_mention`, `message`, `reaction_added`, …). The event must also be enabled in the app's Event Subscriptions.
- **`@app.message("keyword"|regex)`** — sugar over `message` events; needs `message.*` scopes and the `message` event subscribed.
- Match precisely. A bare `@app.event("message")` fires on **every** message the bot can see (including its own and other bots') — filter on `subtype`, `bot_id`, and channel, or you'll create loops.

## The `ack()` discipline
Slack requires acknowledgement of commands, actions, shortcuts, and view submissions **within 3 seconds** or the user sees a timeout error. Call `ack()` (async: `await ack()`) as the **first line**, before any slow work. `ack()` can also carry a response (e.g. `await ack(response_action="errors", errors={...})` to reject a modal). Events (`@app.event`) are auto-acked by Bolt — don't call `ack` there.

## Listener arguments & responding
Bolt injects only the arguments your function names (argument injection by name):
- `event` / `payload` / `body` — the incoming data (`body` is the full envelope).
- `say` — post into the triggering channel/DM.
- `respond` — reply to a command/interaction via its response_url (supports `response_type: "ephemeral"`).
- `client` — a (bot-token) `WebClient`/`AsyncWebClient` for arbitrary Web API calls (`client.views_open`, `client.chat_update`, `client.reactions_add`, …).
- `ack`, `logger`, `context`.

Prefer `say`/`respond` for the common reply; drop to `client` for anything else (opening modals, updating messages, reactions).

## Lazy listeners and long work
An `ack()` must return in 3s, but real work often takes longer. Two patterns:
- **Lazy listeners** (`app.command("/x")(ack=respond_ack, lazy=[do_work])`) — Bolt acks immediately and runs the `lazy` functions separately. The canonical way to do slow work after a fast ack.
- **Offload** — `ack()` first, then hand the work to a background task/queue and post the result later via `client.chat_postMessage` or `respond`. Never block the listener on a long API/LLM call before acking.

## Errors, retries, and idempotency
- Register a global handler with `@app.error` to log and swallow listener exceptions so one bad event doesn't kill the socket.
- **Slack retries events** it thinks failed (it resends with an `X-Slack-Retry-Num` header / `retry` metadata). Make side effects idempotent — dedupe on the event/message `ts` or client_msg_id so a retry doesn't double-post or double-charge.
- Handle Web API rate limits: `slack_sdk` raises `SlackApiError`; respect `Retry-After` (the SDK can retry automatically via configured retry handlers).

## Testing
- Don't hit Slack in tests. Attach a **mock handler** / mock `AsyncWebClient` so listeners run without a live socket or real Web API calls (this also sidesteps the Socket Mode connect-retry that would otherwise block startup).
- Invoke listeners by constructing the event/command payload and asserting on the mock client's calls (`chat_postMessage`, `views_open`) and on `ack` being called. `slack_bolt` request/response test helpers exist, but a mocked client + direct listener invocation is usually the leanest unit test.
