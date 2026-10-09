from __future__ import annotations
import json, logging, subprocess
from typing import Any
LOGGER=logging.getLogger(__name__)
def get_ipv4_for_interface(interface_name: str) -> str | None:
    try:
        r=subprocess.run(['ip','-j','-4','addr','show','dev',interface_name],check=True,capture_output=True,text=True,timeout=2)
        for iface in json.loads(r.stdout or '[]'):
            for addr in iface.get('addr_info',[]):
                if addr.get('local'): return str(addr['local'])
    except Exception as exc: LOGGER.warning('Could not resolve IPv4 for %s: %s',interface_name,exc)
    return None
