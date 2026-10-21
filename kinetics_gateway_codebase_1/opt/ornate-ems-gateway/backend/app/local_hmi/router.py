"""Serve a completely local HMI without a separate frontend web server.

All telemetry comes from the existing protected gateway APIs. The public HTML
shell contains no site telemetry and cannot be used to execute control writes.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

_ROOT = Path(__file__).resolve().parent
router = APIRouter()


@router.get('/hmi', include_in_schema=False)
def hmi_redirect():
    return RedirectResponse('/hmi/', status_code=307)


@router.get('/hmi/', include_in_schema=False)
def hmi_index():
    return FileResponse(_ROOT / 'index.html', media_type='text/html', headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        'Referrer-Policy': 'no-referrer',
    })


@router.get('/hmi/styles.css', include_in_schema=False)
def hmi_styles():
    return FileResponse(_ROOT / 'styles.css', media_type='text/css', headers={'Cache-Control': 'no-cache'})


@router.get('/hmi/app.js', include_in_schema=False)
def hmi_script():
    return FileResponse(_ROOT / 'app.js', media_type='text/javascript', headers={'Cache-Control': 'no-cache'})
