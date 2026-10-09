#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = 'http://127.0.0.1:8000'

def request(method: str, url: str, token: str | None=None, body: dict | None=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            text = r.read().decode('utf-8')
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        text = e.read().decode('utf-8')
        try:
            payload = json.loads(text)
        except Exception:
            payload = {'raw': text}
        raise SystemExit(f'HTTP {e.code}: {json.dumps(payload, indent=2)}') from e

def login(base_url: str, username: str, password: str) -> str:
    res = request('POST', f'{base_url}/api/auth/login', body={'username': username, 'password': password})
    return res['access_token']

def main():
    p = argparse.ArgumentParser(description='NorthBound EMS Gateway control CLI')
    p.add_argument('--base-url', default=DEFAULT_BASE_URL)
    p.add_argument('--username', default='internal')
    p.add_argument('--password', default='Internal@123')
    p.add_argument('--token')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('sources')
    g = sub.add_parser('grid-mode'); g.add_argument('source_id'); g.add_argument('target_mode', choices=['grid_tied','off_grid'])
    c = sub.add_parser('charge'); c.add_argument('source_id'); c.add_argument('power_kw', type=float)
    d = sub.add_parser('discharge'); d.add_argument('source_id'); d.add_argument('power_kw', type=float)
    s = sub.add_parser('standby'); s.add_argument('source_id')
    sg = sub.add_parser('site-grid-mode'); sg.add_argument('target_mode', choices=['grid_tied','off_grid']); sg.add_argument('--order', nargs='*')
    sp = sub.add_parser('site-power'); sp.add_argument('operation', choices=['charge','discharge']); sp.add_argument('total_power_kw', type=float); sp.add_argument('--allocation', choices=['equal','custom'], default='equal'); sp.add_argument('--source', action='append', dest='sources')
    sub.add_parser('site-standby')
    args = p.parse_args()
    base = args.base_url.rstrip('/')
    token = args.token or login(base, args.username, args.password)
    if args.cmd == 'sources':
        res = request('GET', f'{base}/api/sources', token=token)
    elif args.cmd == 'grid-mode':
        res = request('POST', f'{base}/api/control/sources/{args.source_id}/grid-mode', token=token, body={'target_mode': args.target_mode})
    elif args.cmd == 'charge':
        res = request('POST', f'{base}/api/control/sources/{args.source_id}/charge', token=token, body={'power_kw': args.power_kw})
    elif args.cmd == 'discharge':
        res = request('POST', f'{base}/api/control/sources/{args.source_id}/discharge', token=token, body={'power_kw': args.power_kw})
    elif args.cmd == 'standby':
        res = request('POST', f'{base}/api/control/sources/{args.source_id}/standby', token=token, body={})
    elif args.cmd == 'site-grid-mode':
        body = {'target_mode': args.target_mode}
        if args.order:
            body['source_order'] = args.order
        res = request('POST', f'{base}/api/control/site/grid-mode', token=token, body=body)
    elif args.cmd == 'site-power':
        body = {'operation': args.operation, 'total_power_kw': args.total_power_kw, 'allocation': args.allocation}
        if args.sources:
            body['source_ids'] = args.sources
        res = request('POST', f'{base}/api/control/site/power', token=token, body=body)
    elif args.cmd == 'site-standby':
        res = request('POST', f'{base}/api/control/site/standby', token=token, body={})
    print(json.dumps(res, indent=2))

if __name__ == '__main__':
    main()
