from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nb_ems_gateway.config.models import FastBESSLoggerConfig


def _parse_iso_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except Exception:
        return None


class FastBESSLogger:
    """One-second logger for critical PCS/BMS values.

    V2.1 keeps the compact V2 storage format but changes the logger execution
    model from an asyncio task to a dedicated daemon thread.

    Why this matters:
    the main Modbus polling loop is synchronous/blocking while it reads all
    register points. An asyncio logger task can only run between polling cycles,
    so a configured 1-second logger can effectively become 5-7 seconds. A
    dedicated thread can sample the latest AssetManager values every second
    without issuing extra Modbus reads and without waiting for the full poll
    cycle to finish.

    The logger samples the latest values already present in AssetManager. It does
    not issue extra Modbus reads, so it does not disturb gateway polling or the
    control path.
    """

    def __init__(self, config: FastBESSLoggerConfig, container: Any) -> None:
        self.config = config
        self.container = container
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._running = False
        self._profile: dict[str, list[str]] = {}
        self._profile_error: str | None = None
        self.sample_count = 0
        self.write_count = 0
        self.skipped_count = 0
        self.last_error: str | None = None
        self.last_sample_utc: str | None = None
        self.last_cleanup_ts = 0.0
        self.last_cleanup_result: dict[str, Any] | None = None
        self.execution_mode = 'threaded'

    def load_profile(self) -> None:
        path = Path(self.config.profile_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            profiles = data.get('profiles') or {}
            profile = profiles.get(self.config.profile_name)
            if not isinstance(profile, dict):
                raise KeyError(f'profile not found: {self.config.profile_name}')
            assets = profile.get('assets', profile)
            pcs = list(assets.get('pcs_1') or assets.get('pcs') or [])
            bms = list(assets.get('bms_1') or assets.get('bms') or [])
            if not pcs and not bms:
                raise ValueError('profile does not contain pcs_1 or bms_1 signal lists')
            self._profile = {'pcs_1': pcs, 'bms_1': bms}
            self._profile_error = None
        except Exception as exc:
            self._profile = {'pcs_1': [], 'bms_1': []}
            self._profile_error = str(exc)
            raise

    async def start(self) -> None:
        if not self.config.enabled:
            return
        if not self.container.storage:
            self.last_error = 'storage disabled; fast BESS logger cannot start'
            return
        self.load_profile()
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_loop,
            name='fast-bess-logger',
            daemon=True,
        )
        self._thread.start()
        if self.config.log_start_stop_events:
            self.container.event_logger.info(
                'fast_bess_logger_started',
                'Fast BESS PCS/BMS logger started',
                self.status(),
                source='fast_bess_logger',
            )

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            await asyncio.to_thread(self._thread.join, 5.0)
        if self.config.enabled and self.config.log_start_stop_events:
            self.container.event_logger.info(
                'fast_bess_logger_stopped',
                'Fast BESS PCS/BMS logger stopped',
                self.status(),
                source='fast_bess_logger',
            )

    def _thread_loop(self) -> None:
        interval = max(0.1, float(self.config.interval_sec or 1.0))
        next_tick = time.monotonic()
        while not self._stop_event.is_set():
            start = time.monotonic()
            try:
                self.sample_once()
            except Exception as exc:
                self.last_error = str(exc)
                self.skipped_count += 1
                try:
                    self.container.event_logger.error(
                        'fast_bess_logger_error',
                        f'Fast BESS logger sample failed: {exc}',
                        {'error': str(exc)},
                        source='fast_bess_logger',
                    )
                except Exception:
                    pass

            # Stable periodic timing: schedule the next tick from the intended
            # cadence rather than from the end time. If the system is delayed by
            # more than one interval, reset to avoid a catch-up burst.
            next_tick += interval
            delay = next_tick - time.monotonic()
            if delay < -interval:
                next_tick = time.monotonic() + interval
                delay = interval
            self._stop_event.wait(max(0.0, delay))

            # If one sample itself takes longer than the interval, do not spin.
            if time.monotonic() - start > interval and not self._stop_event.is_set():
                time.sleep(0.01)

    def _source_asset_ids(self, source_id: str) -> dict[str, str]:
        mapped = self.config.source_asset_map.get(source_id) or {}
        return {
            'bess_id': mapped.get('bess_id') or source_id.replace('external_ems_', 'bess_'),
            'pcs_asset_id': mapped.get('pcs_asset_id') or f'{source_id}_pcs',
            'bms_asset_id': mapped.get('bms_asset_id') or f'{source_id}_bms',
        }

    def _extract_signals(self, asset_id: str, wanted: list[str], now_ts: float) -> tuple[dict[str, Any], int, int, int | None]:
        asset = self.container.asset_manager.telemetry.get(asset_id, {})
        signals = asset.get('signals', {})
        out: dict[str, Any] = {}
        good = 0
        bad = 0
        ages: list[int] = []
        value_only = self.config.write_mode == 'value_only'

        for signal_name in wanted:
            sig = signals.get(signal_name)
            if not sig:
                out[signal_name] = None if value_only else {'quality': 'missing'}
                bad += 1
                continue

            updated_ts = _parse_iso_ts(sig.get('updated_utc'))
            age_ms = int(max(0.0, now_ts - updated_ts) * 1000) if updated_ts is not None else None
            if age_ms is not None:
                ages.append(age_ms)

            quality = sig.get('quality', 'unknown')
            if quality == 'good':
                good += 1
            else:
                bad += 1

            if value_only:
                out[signal_name] = sig.get('value')
            else:
                out[signal_name] = {
                    'value': sig.get('value'),
                    'unit': sig.get('unit'),
                    'quality': quality,
                    'category': sig.get('category'),
                    'display_name': sig.get('display_name'),
                    'updated_utc': sig.get('updated_utc'),
                    'age_ms': age_ms,
                }
        return out, good, bad, max(ages) if ages else None

    def sample_once(self) -> dict[str, Any]:
        if not self.container.storage:
            self.skipped_count += 1
            return {'ok': False, 'reason': 'storage_disabled'}
        if not self._profile:
            self.load_profile()

        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        epoch_ms = int(now_ts * 1000)
        ts = now.isoformat()
        written: list[dict[str, Any]] = []

        for source_id in self.config.sources:
            ids = self._source_asset_ids(source_id)
            pcs_values, pcs_good, pcs_bad, pcs_age = self._extract_signals(ids['pcs_asset_id'], self._profile.get('pcs_1', []), now_ts)
            bms_values, bms_good, bms_bad, bms_age = self._extract_signals(ids['bms_asset_id'], self._profile.get('bms_1', []), now_ts)
            max_age_ms_values = [v for v in [pcs_age, bms_age] if v is not None]
            max_age_ms = max(max_age_ms_values) if max_age_ms_values else None
            selected = len(self._profile.get('pcs_1', [])) + len(self._profile.get('bms_1', []))
            good = pcs_good + bms_good
            bad = pcs_bad + bms_bad

            if bad == 0:
                quality = 'good'
            elif good > 0:
                quality = 'partial'
            else:
                quality = 'bad'
            if max_age_ms is not None and max_age_ms > int(self.config.max_data_age_sec * 1000):
                quality = 'stale' if good else 'bad'

            sample = {
                'schema_version': 2 if self.config.write_mode == 'value_only' else 1,
                'write_mode': self.config.write_mode,
                'timestamp_utc': ts,
                'timestamp_epoch_ms': epoch_ms,
                'source_id': source_id,
                'bess_id': ids['bess_id'],
                'pcs_asset_id': ids['pcs_asset_id'],
                'bms_asset_id': ids['bms_asset_id'],
                'profile_name': self.config.profile_name,
                'pcs_values': pcs_values,
                'bms_values': bms_values,
                'selected_signal_count': selected,
                'good_signal_count': good,
                'bad_signal_count': bad,
                'max_data_age_ms': max_age_ms,
                'quality': quality,
            }
            row_id = self.container.storage.insert_fast_bess_sample(sample)
            written.append({'source_id': source_id, 'row_id': row_id, 'quality': quality, 'good': good, 'bad': bad})
            if row_id is not None:
                self.write_count += 1

        self.sample_count += 1
        self.last_sample_utc = ts
        self._cleanup_if_due()
        return {'ok': True, 'timestamp_utc': ts, 'written': written}

    def _cleanup_if_due(self) -> None:
        if not self.container.storage:
            return
        now = time.time()
        if now - self.last_cleanup_ts < self.config.cleanup_interval_sec:
            return
        self.last_cleanup_ts = now
        self.last_cleanup_result = self.container.storage.cleanup_fast_bess_samples(self.config.retention_days)

    def expand_item(self, item: dict[str, Any]) -> dict[str, Any]:
        item.setdefault('profile_name', self.config.profile_name)
        item.setdefault('write_mode', self.config.write_mode)
        item.setdefault('schema_version', 2 if self.config.write_mode == 'value_only' else 1)
        return item

    def profile_status(self) -> dict[str, Any]:
        return {
            'profile_name': self.config.profile_name,
            'profile_path': self.config.profile_path,
            'write_mode': self.config.write_mode,
            'pcs_signals': list(self._profile.get('pcs_1', [])),
            'bms_signals': list(self._profile.get('bms_1', [])),
            'pcs_signal_count': len(self._profile.get('pcs_1', [])),
            'bms_signal_count': len(self._profile.get('bms_1', [])),
        }

    def status(self) -> dict[str, Any]:
        return {
            'enabled': self.config.enabled,
            'running': self._running,
            'execution_mode': self.execution_mode,
            'thread_alive': bool(self._thread and self._thread.is_alive()),
            'interval_sec': self.config.interval_sec,
            'retention_days': self.config.retention_days,
            'write_mode': self.config.write_mode,
            'profile_name': self.config.profile_name,
            'profile_path': self.config.profile_path,
            'profile_error': self._profile_error,
            'sources': self.config.sources,
            'pcs_signal_count': len(self._profile.get('pcs_1', [])),
            'bms_signal_count': len(self._profile.get('bms_1', [])),
            'total_signal_count_per_bess': len(self._profile.get('pcs_1', [])) + len(self._profile.get('bms_1', [])),
            'sample_count': self.sample_count,
            'write_count': self.write_count,
            'skipped_count': self.skipped_count,
            'last_sample_utc': self.last_sample_utc,
            'last_cleanup_result': self.last_cleanup_result,
            'last_error': self.last_error,
        }
