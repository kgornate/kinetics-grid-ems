# NorthBound Flutter Dashboard v0.3 WebSocket Fix

Your Python tests proved that both endpoints send WebSocket frames successfully:

```text
ws://192.168.10.2:8000/ws/telemetry
wss://ems-api.unityess.cloud/ws/telemetry
```

So the issue was not the gateway and not Cloudflare. The issue was Flutter-side WebSocket lifecycle handling.

## Fixes added

1. The dashboard now subscribes to the WebSocket stream before calling `connect()`.
2. `didUpdateWidget()` now reconnects WebSocket when the URL/profile changes.
3. The WebSocket client now has auto reconnect after close/error.
4. The dashboard now shows WebSocket state:
   - connecting
   - connected
   - reconnecting
   - disconnected
   - error
5. The dashboard shows last WebSocket error details.
6. Added manual reconnect button in the top-right toolbar.
7. REST polling remains active even if WebSocket has an issue.

## Expected result

After launching the app, the top chip should change from:

```text
WS connecting: 0
```

to something like:

```text
WS connected: 1
WS connected: 2
WS connected: 3
```

If the gateway or Cloudflare path disconnects, the app should show `reconnecting` and retry automatically.

## No gateway change required

The gateway WebSocket endpoint already works. Cloudflare WebSocket forwarding also already works. This release is only a Flutter-side reliability fix.
