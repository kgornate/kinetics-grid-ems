"""View/formatting helpers kept independent of GTK for host-side unit tests."""
from __future__ import annotations

from datetime import datetime, timezone
import math


def txt(value, maxlen=90):
    if value is None or value == '':
        return '—'
    s = str(value)
    return s if len(s) <= maxlen else s[:maxlen - 1] + '…'


def fmt(value, digits=1, unit=''):
    if value is None or isinstance(value, bool):
        return '—'
    try:
        val = float(value)
        if not math.isfinite(val):
            return '—'
    except (ValueError, TypeError, OverflowError):
        return '—'
    return f'{val:.{digits}f}{unit}'


def onoff(value):
    return 'ONLINE' if value is True else 'OFFLINE' if value is False else 'UNKNOWN'


def pcs_state(p):
    return 'Running' if p.get('running') is True else 'Standby' if p.get('standby') is True else 'Stopped' if p.get('running') is False else '—'


def pairs(model):
    return sorted((p for p in (model.get('pairs') or {}).values() if isinstance(p, dict)),
                  key=lambda p: str(p.get('pair_id', '')))


def racks(model):
    return sorted((p for p in (model.get('battery_racks') or {}).values() if isinstance(p, dict)),
                  key=lambda p: int(p.get('rack_id') or 0))


def pcss(model):
    return sorted((p for p in (model.get('pcs') or {}).values() if isinstance(p, dict)),
                  key=lambda p: str(p.get('asset_id', '')))


def overview_stats(model, health, alarms):
    enabled = [p for p in pairs(model) if p.get('enabled') is not False]
    b = model.get('battery_system') or {}
    powers = [(p.get('pcs') or {}).get('active_power_kw') for p in enabled
              if (p.get('pcs') or {}).get('online') is True]
    all_valid = bool(enabled) and len(powers) == len(enabled) and all(
        p is not None and fmt(p) != '—' for p in powers)
    total = sum(float(p) for p in powers) if all_valid else None
    alarms_shown = len(alarms.get('alarms') or [])
    return [
        ('Battery SOC', fmt(b.get('soc_percent'), 1, '%')),
        ('PCS active power', fmt(total, 1, ' kW')),
        ('Connected pairs', f'{sum(p.get("online") is True for p in enabled)} / {len(enabled)}'),
        ('Active alarms shown', f'{alarms_shown} (max 100)'),
    ]


def voltage_cell(value):
    """Flag implausible voltages; never guess or silently rescale source units."""
    number = fmt(value, 3, ' V')
    try:
        v = float(value)
    except (ValueError, TypeError):
        return number
    return number + '  [CHECK SCALE]' if math.isfinite(v) and (v > 10 or v < 0) else number


def telemetry_freshness(model, health, now=None):
    timestamp = model.get('timestamp')
    if not timestamp:
        return 'DATA STALE', 'No valid telemetry timestamp'
    try:
        sample = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
        if sample.tzinfo is None:
            return 'DATA STALE', 'Telemetry timestamp has no timezone'
        now = now or datetime.now(timezone.utc)
        delta = (now - sample.astimezone(timezone.utc)).total_seconds()
        if delta > 20 or delta < -120:
            return 'DATA STALE', 'Last snapshot is %.0f seconds old / clock mismatch' % delta
    except (ValueError, OverflowError):
        return 'DATA STALE', 'Invalid telemetry timestamp'
    if health.get('status') != 'ok':
        return 'GATEWAY DEGRADED', 'Gateway status is not OK'
    return 'GATEWAY ONLINE', ''


def battery_rows(model):
    results = []
    for r in racks(model):
        contact = ('Closed' if r.get('positive_contactor_closed') is True and r.get('negative_contactor_closed') is True
                   else 'Open' if r.get('positive_contactor_closed') is False or r.get('negative_contactor_closed') is False
                   else '—')
        results.append([f'Rack {txt(r.get("rack_id"))}', onoff(r.get('online')),
                        fmt(r.get('soc_percent'), 1, '%'), fmt(r.get('soh_percent'), 1, '%'),
                        fmt(r.get('voltage_v'), 1, ' V'), fmt(r.get('current_a'), 1, ' A'),
                        txt(r.get('state')), fmt(r.get('max_charge_power_kw'), 1, ' kW'),
                        fmt(r.get('max_discharge_power_kw'), 1, ' kW'), contact])
    return results


def pcs_rows(model):
    results = []
    for p in pcss(model):
        results.append([txt(p.get('asset_id')), onoff(p.get('online')), pcs_state(p),
                        'Charging' if p.get('charging') is True else 'Discharging' if p.get('discharging') is True else '—',
                        fmt(p.get('active_power_kw'), 1, ' kW'), fmt(p.get('reactive_power_kvar'), 1, ' kVAr'),
                        fmt(p.get('dc_voltage_v'), 1, ' V'), fmt(p.get('dc_current_a'), 1, ' A'),
                        fmt(p.get('grid_frequency_hz'), 2, ' Hz'),
                        'Fault' if p.get('faulted') is True else 'Clear' if p.get('faulted') is False else '—'])
    return results


def alarm_rows(alarms):
    return [[txt(a.get('severity')), txt(a.get('asset_id') or 'Gateway'),
             txt(a.get('alarm_key') or a.get('code') or a.get('signal_name'), 160),
             txt(a.get('state') or 'Active'),
             txt(a.get('first_seen_at') or a.get('first_seen') or a.get('timestamp'))]
            for a in (alarms.get('alarms') or []) if isinstance(a, dict)]


def control_rows(ctrl):
    return [[txt(p.get('pair_id')), txt(p.get('stage')), txt(p.get('run_status')), txt(p.get('direction')),
             fmt(p.get('requested_power_kw'), 1, ' kW'), fmt(p.get('commanded_power_kw'), 1, ' kW'),
             fmt(p.get('pcs_actual_power_kw'), 1, ' kW'),
             'Yes' if p.get('hard_blocked') is True else 'No' if p.get('hard_blocked') is False else '—']
            for p in (ctrl.get('pairs') or {}).values() if isinstance(p, dict)]
