from __future__ import annotations

import json
import logging
import socket
import subprocess
from typing import Any

LOGGER = logging.getLogger(__name__)


def get_ipv4_for_interface(interface_name: str) -> str | None:
    """Return the first IPv4 address configured on a Linux interface.

    The gateway can upload via Wi-Fi now and later switch to Ethernet just by
    changing config. Binding the HTTPS client to the interface source IP helps
    force the outbound connection over the requested network path when routing
    allows it.
    """
    if not interface_name:
        return None
    try:
        result = subprocess.run(
            ["ip", "-j", "-4", "addr", "show", "dev", interface_name],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        data: list[dict[str, Any]] = json.loads(result.stdout or "[]")
        for iface in data:
            for addr in iface.get("addr_info", []):
                local = addr.get("local")
                if local:
                    return str(local)
    except Exception as exc:
        LOGGER.warning("Could not resolve IPv4 address for interface %s: %s", interface_name, exc)
    return None


def host_reachable(host: str, port: int, *, timeout_sec: float = 2.0, source_ip: str | None = None) -> bool:
    """Best-effort TCP connectivity check used by diagnostics and upload status."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        if source_ip:
            sock.bind((source_ip, 0))
        sock.connect((host, port))
        sock.close()
        return True
    except Exception:
        return False
