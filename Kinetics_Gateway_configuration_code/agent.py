#!/usr/bin/env python3
"""Kalpa commissioning API. Python stdlib only; never executes a shell."""
import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONFIG = Path('/etc/wpa_supplicant/mlan0.conf')
STATE = Path('/var/lib/kalpa-setup')


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError('Gateway command failed: ' + args[0])
    return result.stdout.strip()


def atomic(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.new')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def decode_ssid(value):
    # wpa_cli escapes non-printable bytes and backslashes; preserve exact bytes.
    data = bytearray()
    i = 0
    while i < len(value):
        if value[i:i+2] == '\\x' and re.fullmatch('[0-9a-fA-F]{2}', value[i+2:i+4]):
            data.append(int(value[i+2:i+4], 16)); i += 4
        elif value[i:i+2] == '\\\\':
            data.append(92); i += 2
        else:
            data.extend(value[i].encode()); i += 1
    return bytes(data)


def parse_scan(raw):
    networks = []
    for line in raw.splitlines():
        fields = line.split('\t', 4)
        if len(fields) != 5 or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', fields[0]):
            continue
        ssid = decode_ssid(fields[4])
        flags = fields[3]
        supported = bool(ssid) and 'PSK' in flags and 'EAP' not in flags
        try:
            signal = int(fields[2])
        except ValueError:
            continue
        networks.append(dict(ssid=ssid.decode('utf-8', 'replace'), ssid_hex=ssid.hex(),
                             signal_dbm=signal, security=flags, supported=supported))
    return sorted(networks, key=lambda x: x['signal_dbm'], reverse=True)


def build_config(ssid_hex, password):
    try:
        ssid = bytes.fromhex(ssid_hex)
    except (ValueError, TypeError):
        raise ValueError('Invalid SSID hex')
    if not 1 <= len(ssid) <= 32:
        raise ValueError('SSID must be 1–32 bytes')
    if not isinstance(password, str) or not 8 <= len(password.encode('utf-8')) <= 63:
        raise ValueError('WPA password must be 8–63 bytes')
    psk = hashlib.pbkdf2_hmac('sha1', password.encode(), ssid, 4096, 32).hex()
    return ('ctrl_interface=/run/wpa_supplicant\nupdate_config=0\nnetwork={\n'
            f'    ssid={ssid.hex()}\n    psk={psk}\n    key_mgmt=WPA-PSK\n}}\n').encode()


class Backend:
    def status(self):
        values = dict(line.split('=', 1) for line in run('wpa_cli', '-i', 'mlan0', 'status').splitlines() if '=' in line)
        addresses = json.loads(run('ip', '-j', '-4', 'addr', 'show', 'dev', 'mlan0'))
        ips = [a['local'] for iface in addresses for a in iface.get('addr_info', []) if a.get('scope') == 'global']
        state = subprocess.run(['systemctl', 'is-active', 'cloudflared.service'], capture_output=True, text=True, timeout=5)
        link = run('iw', 'dev', 'mlan0', 'link')
        signal = re.search(r'signal:\s*(-?\d+)', link)
        return dict(ssid=decode_ssid(values.get('ssid', '')).decode('utf-8', 'replace'),
                    ssid_hex=decode_ssid(values.get('ssid', '')).hex(),
                    connected=values.get('wpa_state') == 'COMPLETED', ipv4=ips,
                    signal_dbm=int(signal[1]) if signal else None,
                    cloudflared_service=state.stdout.strip(),
                    tunnel_connectivity='not_verified')

    def scan(self):
        answer = run('wpa_cli', '-i', 'mlan0', 'scan')
        if answer != 'OK':
            raise RuntimeError('Wi-Fi scan unavailable; try again')
        time.sleep(3)
        return parse_scan(run('wpa_cli', '-i', 'mlan0', 'scan_results'))

    def reconnect(self):
        run('systemctl', 'restart', 'debix-wifi.service')
        run('systemctl', 'restart', 'debix-wifi-dhcp.service')


class Manager:
    def __init__(self, backend, config=CONFIG, state=STATE, timeout=90):
        self.backend, self.config, self.state, self.timeout = backend, Path(config), Path(state), timeout
        self.lock = threading.RLock()
        self.operation = None
        self.deadline = 0
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        # A persisted backup means the last change was never confirmed (including power loss).
        if (self.state / 'pending-backup').exists():
            self.restore()

    def restore(self):
        atomic(self.config, (self.state / 'pending-backup').read_bytes())
        self.backend.reconnect()
        (self.state / 'pending-backup').unlink()

    def apply(self, ssid_hex, password):
        data = build_config(ssid_hex, password)
        with self.lock:
            if (self.state / 'pending-backup').exists():
                raise ValueError('A Wi-Fi change is already pending')
            atomic(self.state / 'pending-backup', self.config.read_bytes())
            self.operation = dict(id=secrets.token_hex(12), state='applying', ssid_hex=bytes.fromhex(ssid_hex).hex())
            self.deadline = time.monotonic() + self.timeout
            threading.Thread(target=self.worker, args=(self.operation['id'], data), daemon=True).start()
            return dict(self.operation)

    def worker(self, op_id, data):
        try:
            atomic(self.config, data)
            self.backend.reconnect()
            with self.lock:
                if self.operation['id'] == op_id:
                    self.operation['state'] = 'awaiting_confirmation'
            while time.monotonic() < self.deadline:
                with self.lock:
                    if self.operation['id'] != op_id or self.operation['state'] == 'confirmed':
                        return
                time.sleep(.25)
            self.rollback(op_id)
        except Exception:
            self.rollback(op_id)

    def rollback(self, op_id):
        with self.lock:
            if self.operation['id'] != op_id or self.operation['state'] == 'confirmed':
                return
            try:
                self.restore()
                self.operation['state'] = 'rolled_back'
            except Exception:
                self.operation['state'] = 'rollback_failed'

    def confirm(self, op_id):
        with self.lock:
            if not self.operation or self.operation['id'] != op_id:
                raise ValueError('Unknown operation')
            if self.operation['state'] == 'confirmed':
                return dict(self.operation)
            if self.operation['state'] != 'awaiting_confirmation' or time.monotonic() >= self.deadline:
                raise ValueError('Change cannot be confirmed')
            status = self.backend.status()
            if not (status['connected'] and status['ipv4'] and status['ssid_hex'] == self.operation['ssid_hex']):
                raise ValueError('Selected Wi-Fi is not connected with an IP address yet')
            (self.state / 'pending-backup').unlink()
            self.operation['state'] = 'confirmed'
            return dict(self.operation)

    def status(self):
        with self.lock:
            return dict(self.operation) if self.operation else None


def handler(manager, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log credentials, tokens or request bodies.

        def respond(self, code, data):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def handle_api(self):
            self.connection.settimeout(5)
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                return self.respond(401, {'error': 'Invalid setup token'})
            if self.headers.get('Origin'):
                return self.respond(403, {'error': 'Browser requests are not supported'})
            try:
                if self.command == 'GET' and self.path == '/v1/connectivity':
                    import sys
                    probe = Path(__file__).with_name('connectivity.py')
                    try:
                        output = subprocess.run([sys.executable, str(probe)], capture_output=True,
                                                text=True, timeout=22, check=True)
                        return self.respond(200, json.loads(output.stdout))
                    except subprocess.TimeoutExpired:
                        return self.respond(200, {'checks': {'internet': {'state': 'unknown',
                            'detail': 'Diagnostics timed out; no pass result is claimed'}}})
                if self.command == 'GET' and self.path == '/v1/status':
                    return self.respond(200, {'wifi': manager.backend.status(), 'operation': manager.status()})
                if self.command == 'GET' and self.path == '/v1/wifi/scan':
                    return self.respond(200, {'networks': manager.backend.scan()})
                if self.command != 'POST' or self.path not in ('/v1/wifi/apply', '/v1/wifi/confirm'):
                    return self.respond(404, {'error': 'Unknown endpoint'})
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    return self.respond(415, {'error': 'JSON required'})
                length = int(self.headers.get('Content-Length', '0'))
                if not 1 <= length <= 4096:
                    return self.respond(400, {'error': 'Invalid body size'})
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('JSON object required')
                if self.path.endswith('/apply'):
                    result = manager.apply(body.get('ssid_hex'), body.get('password'))
                else:
                    result = manager.confirm(body.get('operation_id'))
                return self.respond(200, {'operation': result})
            except (ValueError, TypeError, KeyError):
                return self.respond(400, {'error': 'Invalid request or Wi-Fi change not ready; refresh status'})
            except Exception:
                import traceback
                traceback.print_exc()
                return self.respond(503, {'error': 'Gateway operation unavailable; check local service logs'})
        do_GET = handle_api
        do_POST = handle_api
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='192.168.10.2')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--interface', default='eth0')
    args = parser.parse_args()
    token = (STATE / 'token').read_text().strip()
    if len(token) < 32:
        raise SystemExit('Setup token is missing or too short')
    manager = Manager(Backend())
    server = ThreadingHTTPServer((args.host, args.port), handler(manager, token), bind_and_activate=False)
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, args.interface.encode() + b'\0')
    server.server_bind()
    server.server_activate()
    server.serve_forever()
