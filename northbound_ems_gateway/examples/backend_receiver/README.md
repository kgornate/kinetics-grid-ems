# Example Backend Receiver

This is a minimal FastAPI backend receiver for testing the gateway HTTPS REST upload payload.

In production, this endpoint should run behind HTTPS using Nginx/Caddy/Traefik/cloud load balancer. For local lab testing, it can run over plain HTTP.

## Run locally

```bash
pip install fastapi uvicorn
BACKEND_API_TOKEN=CHANGE_ME_API_TOKEN uvicorn receiver:app --host 0.0.0.0 --port 9000
```

Configure gateway:

```json
"server_upload": {
  "enabled": true,
  "transport": "https_rest",
  "endpoint_url": "http://SERVER_IP:9000/api/v1/gateway/telemetry",
  "api_key": "CHANGE_ME_API_TOKEN",
  "network_interface": "mlan0"
}
```

For real deployment, use an HTTPS URL.
