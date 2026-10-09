import os


MARKER_FILE = "/etc/nb_ems_block_public_http"

PUBLIC_HOSTS = {
    "ems-api.unityess.cloud",
    "ems-logs.unityess.cloud",
}


class PublicHttpMaintenanceMiddleware:
    """
    Blocks only public/Cloudflare HTTP and WebSocket traffic when
    MARKER_FILE exists.

    Localhost/direct internal API access remains available.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):

        scope_type = scope.get("type")

        if scope_type not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Dynamic switch:
        # no gateway restart is required when enabling/disabling later.
        if not os.path.exists(MARKER_FILE):
            await self.app(scope, receive, send)
            return

        headers = {
            k.lower(): v
            for k, v in scope.get("headers", [])
        }

        host = headers.get(b"host", b"").decode(
            "latin-1",
            errors="ignore"
        ).split(":")[0].lower()

        cf_connecting_ip = headers.get(b"cf-connecting-ip")
        cf_ray = headers.get(b"cf-ray")
        x_forwarded_for = headers.get(b"x-forwarded-for")

        # Primary detection: public hostname.
        # Fallback detection: Cloudflare proxy headers.
        is_public_request = (
            host in PUBLIC_HOSTS
            or cf_connecting_ip is not None
            or cf_ray is not None
            or (
                x_forwarded_for is not None
                and host in PUBLIC_HOSTS
            )
        )

        if not is_public_request:
            await self.app(scope, receive, send)
            return

        if scope_type == "websocket":
            await send({
                "type": "websocket.close",
                "code": 1013,
                "reason": "Public gateway access temporarily disabled",
            })
            return

        body = b"Public gateway API temporarily disabled\n"

        response_headers = [
            (b"content-type", b"text/plain"),
            (b"content-length", str(len(body)).encode()),
            (b"cache-control", b"no-store"),
            (b"retry-after", b"3600"),
            (b"connection", b"close"),
        ]

        await send({
            "type": "http.response.start",
            "status": 503,
            "headers": response_headers,
        })

        await send({
            "type": "http.response.body",
            "body": body,
        })


def install_public_http_maintenance(app):

    # Avoid accidental duplicate installation.
    state = getattr(app, "state", None)

    if state is not None:
        if getattr(
            state,
            "_public_http_maintenance_installed",
            False
        ):
            return

    app.add_middleware(PublicHttpMaintenanceMiddleware)

    if state is not None:
        state._public_http_maintenance_installed = True
