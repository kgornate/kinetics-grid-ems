# v0.8 Network Timeout and Connection Profile Update

## Problem fixed

Cloudflare/remote mode can be much slower than direct local Ethernet for large asset payloads. Local eth0 calls usually respond within a few seconds, but full BMS telemetry through Cloudflare/hotspot can take 10-15 seconds or more. The earlier Flutter client used a fixed 5 second timeout for every HTTP request, so asset detail pages could fail even though the gateway and Cloudflare tunnel were working.

## New profile-based architecture

The app now uses one active `ApiProfile` everywhere:

```dart
class ApiProfile {
  final String name;
  final String restBaseUrl;
  final String wsUrl;
  final String logsBaseUrl;
  final Duration httpTimeout;
}
```

Default profiles:

```text
Local eth0
REST: http://192.168.10.2:8000
WS:   ws://192.168.10.2:8000/ws/telemetry
HTTP timeout: 5 seconds

Cloudflare
REST: https://ems-api.unityess.cloud
WS:   wss://ems-api.unityess.cloud/ws/telemetry
HTTP timeout: 30 seconds
```

## Pages covered

The same active profile is used by:

- dashboard health polling
- asset discovery/cards
- asset detail page
- full asset telemetry calls such as `/api/assets/bms_1/telemetry`
- logs/gateway events page
- historian/storage pages
- storage status calls
- alarm page
- WebSocket connection

## SSE endpoint removed

The Flutter app does not call the old SSE endpoint:

```text
/api/stream/telemetry
```

The active live stream endpoint is WebSocket:

```text
/ws/telemetry
```

Cloudflare must use `wss://`, while local eth0 uses `ws://`.

## Notes about logsBaseUrl

NorthBound v0.5 exposes `/api/logs` and `/api/storage` through the main REST API on port 8000. Therefore, the default `logsBaseUrl` is the same as `restBaseUrl` for both local eth0 and Cloudflare. If a later deployment exposes the same v0.5 log routes on a separate log domain, only `logsBaseUrl` needs to be changed.
