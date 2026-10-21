"""Loopback-only, read-only gateway API client (login is the sole POST)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class APIError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class GatewayClient:
    PATHS = (
        '/api/normalized/snapshot',
        '/api/health',
        '/api/alarms?active_only=true&limit=100',
        '/api/control-sequence/status/all/compact',
    )

    def __init__(self, base_url: str = 'http://127.0.0.1:8000'):
        u = urlsplit(base_url)
        if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1') or u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
            raise ValueError('Native HMI connects only to a local HTTP gateway (loopback)')
        self.base_url = base_url.rstrip('/')
        self.token: str | None = None
        self.role = 'viewer'

    def _request(self, path: str, payload: dict | None = None, authenticated: bool = True) -> dict:
        if not path.startswith('/api/'):
            raise ValueError('Only gateway API paths are permitted')
        if payload is not None and path != '/api/auth/login':
            raise ValueError('Control/write endpoints are not supported')
        headers = {'Accept': 'application/json', 'Cache-Control': 'no-store'}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        if authenticated:
            if not self.token:
                raise APIError('Authentication required', 401)
            headers['Authorization'] = 'Bearer ' + self.token
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers,
                                     method='POST' if data is not None else 'GET')
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                decoded = json.load(resp)
                if not isinstance(decoded, dict):
                    raise APIError('Unexpected API response format')
                return decoded
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise APIError('Incorrect credentials or session expired', 401) from e
            raise APIError('Gateway returned HTTP %s' % e.code, e.code) from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise APIError('Cannot reach local gateway: %s' % str(e.reason if hasattr(e, 'reason') else e)) from e
        except (ValueError, json.JSONDecodeError) as e:
            raise APIError('Invalid JSON returned by gateway') from e

    def login(self, username: str, password: str) -> str:
        result = self._request('/api/auth/login', {'username': username, 'password': password}, False)
        if not isinstance(result.get('access_token'), str) or not result['access_token']:
            raise APIError('Login returned no token')
        self.token = result['access_token']
        self.role = str(result.get('role', 'viewer'))
        return self.role

    def logout(self) -> None:
        self.token = None
        self.role = 'viewer'

    def poll(self) -> tuple[dict, dict, dict, dict]:
        return tuple(self._request(path) for path in self.PATHS)
