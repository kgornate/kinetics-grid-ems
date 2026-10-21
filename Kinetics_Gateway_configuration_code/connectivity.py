"""Bounded diagnostics invoked as a subprocess by the setup agent. No mutations."""
import concurrent.futures
import datetime
import http.client
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import time


def command(*args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=3)
    return p.stdout.strip()


def result(state, detail, **extra):
    return dict(state=state, detail=detail, **extra)


def route():
    rows = json.loads(command('ip', '-j', 'route', 'get', '1.1.1.1'))
    row = rows[0] if rows else {}
    dev = row.get('dev', 'unknown')
    return result('pass' if dev == 'mlan0' else 'warning',
                  'Default internet route uses ' + dev, interface=dev)


def resolve(host):
    return list(dict.fromkeys(a[4][0] for a in socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)))


def wifi_https(host, path, expected):
    addresses = resolve(host)
    start = time.monotonic()
    last = None
    for address in addresses[:2]:
        conn = None
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(4)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b'mlan0\0')
            sock.connect((address, 443))
            tls = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            conn = http.client.HTTPSConnection(host, timeout=4)
            conn.sock = tls
            conn.request('GET', path, headers={'Connection': 'close', 'Cache-Control': 'no-cache'})
            response = conn.getresponse()
            body = response.read(4096)
            valid = response.status == expected and (expected != 200 or b'ip=' in body)
            return result('pass' if valid else 'fail',
                          f'{host}: HTTPS {response.status} via mlan0',
                          http_status=response.status, elapsed_ms=round((time.monotonic()-start)*1000))
        except Exception as exc:
            last = type(exc).__name__
        finally:
            if conn: conn.close()
            sock.close()
    return result('fail', f'{host}: Wi-Fi HTTPS failed ({last})')


def dns():
    addresses = resolve('www.cloudflare.com')
    return result('pass' if addresses else 'fail',
                  'System DNS resolved www.cloudflare.com' if addresses else 'No DNS addresses returned')


def local_request(port, path):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=.8)
    try:
        conn.request('GET', path, headers={'Connection': 'close', 'Cache-Control': 'no-cache'})
        response = conn.getresponse()
        return response.status, response.read(8192)
    finally:
        conn.close()


def listener_ports(pid):
    """Only query sockets owned by this systemd service's MainPID."""
    inodes = set()
    for p in (Path('/proc') / str(pid) / 'fd').iterdir():
        try:
            match = re.fullmatch(r'socket:\[(\d+)\]', os.readlink(p))
            if match: inodes.add(match[1])
        except OSError:
            pass
    ports = set()
    for name in ('tcp', 'tcp6'):
        for line in (Path('/proc') / str(pid) / 'net' / name).read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) > 9 and fields[3] == '0A' and fields[9] in inodes:
                address, port = fields[1].split(':')
                # Loopback/wildcard only; do not probe arbitrary remote targets.
                if address in ('0100007F', '00000000', '0'*32, '00000000000000000000000001000000'):
                    ports.add(int(port, 16))
    return sorted(ports)


def classify_ready(status, body):
    try:
        data = json.loads(body)
        count = data.get('readyConnections')
        if isinstance(count, bool) or not isinstance(count, (int, float)) or count < 0:
            return result('unknown', 'Readiness response has no valid connection count')
        if status == 200 and count > 0:
            return result('pass', f'Cloudflared reports {int(count)} ready edge connection(s)', ready_connections=int(count))
        return result('fail', f'Cloudflared readiness HTTP {status}, {int(count)} ready connection(s)', ready_connections=int(count))
    except (ValueError, TypeError, AttributeError):
        return result('unknown', 'Readiness endpoint unavailable in this cloudflared version')


def tunnel():
    state = command('systemctl', 'is-active', 'cloudflared.service')
    if state != 'active':
        return result('fail', 'Cloudflared service is ' + (state or 'unavailable'))
    pid = command('systemctl', 'show', 'cloudflared.service', '--property=MainPID', '--value')
    if not pid.isdigit() or int(pid) == 0:
        return result('unknown', 'Service running; unable to identify tunnel process')
    try:
        ports = listener_ports(int(pid))
    except OSError:
        return result('unknown', 'Service running; cannot inspect its local readiness listener')
    for port in ports[:8]:
        try:
            status, body = local_request(port, '/ready')
            check = classify_ready(status, body)
            if check['state'] != 'unknown':
                return check
        except Exception:
            pass
    return result('unknown', 'Service running; local tunnel readiness endpoint unavailable. No Cloudflare configuration was changed.')


def origin():
    try:
        status, _ = local_request(8000, '/hmi/')
        if status == 200:
            return result('pass', 'Local HMI returned HTTP 200 on port 8000')
        if status in (401, 403):
            return result('warning', f'Local origin requires authentication (HTTP {status})')
        return result('fail', f'Local HMI returned HTTP {status}')
    except Exception as exc:
        return result('fail', 'Local HMI unavailable: ' + type(exc).__name__)


def safe(fn):
    try:
        return fn()
    except Exception as exc:
        return result('fail', 'Check failed: ' + type(exc).__name__)


def checks():
    jobs = {'route': route, 'dns': dns, 'https_cloudflare': lambda: wifi_https('www.cloudflare.com', '/cdn-cgi/trace', 200),
            'https_independent': lambda: wifi_https('www.google.com', '/generate_204', 204),
            'tunnel': tunnel, 'local_hmi': origin}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {key: pool.submit(safe, fn) for key, fn in jobs.items()}
        values = {key: f.result() for key, f in futures.items()}
    online = any(values[k]['state'] == 'pass' for k in ('https_cloudflare', 'https_independent'))
    values['internet'] = result('pass' if online else 'fail',
        'Validated HTTPS response through gateway Wi-Fi' if online else 'Neither configured HTTPS test succeeded; check DNS, Wi-Fi, captive portal, clock or firewall')
    return {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'checks': values}


if __name__ == '__main__':
    print(json.dumps(checks()))
