<!--
library: websockets
versions-covered: "websockets 16.x (asyncio) + FastAPI WS"   # current stable websockets 16.1
last-verified: 2026-07-12
provenance: auto-generated (pending review)
sources:
  - https://pypi.org/project/websockets/
  - https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html
  - https://websockets.readthedocs.io/en/stable/faq/client.html
  - https://github.com/python-websockets/websockets/blob/main/src/websockets/asyncio/client.py
  - https://fastapi.tiangolo.com/advanced/websockets/
-->

# WebSockets conventions

Idioms for the long-lived real-time layer: the `websockets` library as a **client** consuming streaming market data, and FastAPI/Starlette WebSocket endpoints **serving** clients. Read after detecting `websockets` in the manifest, or a FastAPI app with `@app.websocket`. Subordinate to project conventions — if the app already has a stream client or connection manager, match it.

## Contents
- Version check
- Client: connect + reconnect-with-backoff
- Client: heartbeats & dead-connection detection
- Client: backpressure & parsing
- Client: auth on connect
- Server: FastAPI endpoint & receive loop
- Server: broadcasting (connection manager & its limits)
- Server: auth, concurrency, blocking work
- Message schema, shutdown, testing

## Version check (do this first)
- Current stable is **websockets 16.x** (16.1), Python **>=3.10**. Use the **new asyncio API**: `from websockets.asyncio.client import connect`. The `websockets.legacy.*` and top-level `websockets.connect` (client) map to the deprecated legacy stack — **don't** write new code against it.
- `websockets` is the client/standalone-server lib. **FastAPI/Starlette ship their own WS layer** (`WebSocket`, `WebSocketDisconnect`) — different API, do not import `websockets` types in a FastAPI handler.

## Client: connect + reconnect-with-backoff
Connections **drop** — a stream client that doesn't reconnect is broken. `connect` used as an **async iterator** already reconnects with exponential backoff; each iteration yields a fresh live connection:
```python
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

async for ws in connect(URI, open_timeout=10):
    try:
        async for raw in ws:          # auto-iterates messages until close
            handle(raw)
    except ConnectionClosed:
        continue                      # loop reconnects with backoff
```
Retryable errors (`OSError`, `TimeoutError`, `EOFError`, HTTP 500/502/503/504) are retried by the default `process_exception`; everything else breaks the loop and raises. Customize with `process_exception=` to widen/narrow that. Anti-pattern: a single `async with connect(...)` with no outer loop — one drop kills the stream forever.

## Client: heartbeats & dead-connection detection
Keep-alive is **on by default**: `ping_interval=20`, `ping_timeout=20`. If a pong doesn't return within `ping_timeout`, the connection is declared dead and closed (→ triggers reconnect above) — this is how you notice a silently-wedged TCP link. Tune, don't disable: `ping_interval=None` blinds you to half-open connections. For a chatty feed a shorter `ping_timeout` fails over faster.

## Client: backpressure & parsing
The read loop (`async for raw in ws`) must **not block**. Do parse-and-dispatch fast; hand slow work (DB writes, indicators) to a `asyncio.Queue` drained by a separate task. If you can't keep up, the library applies backpressure (bounded buffers) — a blocked consumer eventually stalls reads and trips `ping_timeout`. Parse with **orjson** (`orjson.loads`) not stdlib `json` for hot market-data paths. Cap untrusted payloads with `max_size` (default 1 MB).

## Client: auth on connect
Non-browser clients can set real headers — pass credentials at handshake, not in a post-connect message:
```python
connect(URI, additional_headers={"Authorization": f"Bearer {token}"})
```
For token-in-URL schemes use the query string. Refresh short-lived tokens on each reconnect (re-read from the auth source inside the `async for`), not once at startup.

## Server: FastAPI endpoint & receive loop
```python
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()          # required before any send/receive
    try:
        while True:
            msg = await websocket.receive_json()
            await websocket.send_json(handle(msg))
    except WebSocketDisconnect:
        manager.remove(websocket)     # client vanished — clean up, don't crash
```
Always wrap the loop and catch `WebSocketDisconnect`; an uncaught one spams logs and leaks registrations.

## Server: broadcasting (connection manager & its limits)
In-memory manager pattern: a `set[WebSocket]`, add on connect, discard on disconnect, iterate to fan out. Send under `try/except` and prune dead sockets. **Critical limit:** this is **per-process** — with multiple Uvicorn/Gunicorn workers, a client on worker A never sees a broadcast originating on worker B. To fan out across workers/hosts, publish to **Redis pub/sub** and have each process forward its channel to its local sockets (see redis.md). Don't scale by pinning all clients to one worker.

## Server: auth, concurrency, blocking work
- **Auth:** browsers can't set arbitrary WS headers — authenticate via **query param token**, cookie, or subprotocol, validated *before* `accept()` (`await websocket.close(code=1008)` to reject). `Depends`/`Query`/`Cookie` work in WS handlers.
- **Concurrency:** if you both push server-originated data and read client messages, run **one reader task and one writer task** (`asyncio.create_task`) — a single loop can't `await receive` and `await send` at once.
- **No blocking work** in the handler — a sync DB/CPU call freezes the event loop for *all* connections. Offload to a threadpool / task queue.

## Message schema, shutdown, testing
- Version every message: `{"v": 1, "type": "quote", ...}`. Validate inbound with Pydantic; ignore unknown `type` forward-compatibly.
- **Graceful shutdown:** on lifespan shutdown, close each socket with code 1001 (going away) so clients reconnect elsewhere instead of erroring.
- **Test** with `TestClient`: `with client.websocket_connect("/ws") as ws: ws.send_json(...); assert ws.receive_json() == ...`. For the async client, drive it under `pytest-asyncio` against a local `serve(...)`. Load-test long-lived fan-out separately — unit tests won't surface backpressure or per-worker broadcast gaps.
