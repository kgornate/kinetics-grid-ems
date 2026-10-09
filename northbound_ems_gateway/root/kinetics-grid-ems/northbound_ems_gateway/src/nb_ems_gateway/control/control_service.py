from __future__ import annotations
import asyncio
import time
from typing import Any

from nb_ems_gateway.dictionary.register_map import RegisterPoint

GRID_TIED = 'grid_tied'
OFF_GRID = 'off_grid'

class ControlService:
    def __init__(self, container: Any, readers: dict[str, Any]) -> None:
        self.container = container
        self.readers = readers
        self.control_signals = {
            'grid_switch': 'on_off_grid_switching',
            'charge_kw': 'manual_charge_value_setting',
            'discharge_kw': 'manual_discharge_value_setting',
            'grid_status': 'pcs_on_off_grid_status',
            'va': 'phase_a_voltage',
            'vb': 'phase_b_voltage',
            'vc': 'phase_c_voltage',
            'remote_mode': 'remote_mode',
            'manual_auto_mode': 'manual_auto_mode',
            'manual_mode_control': 'manual_mode_control',
        }

    def validate_source_id(self, source_id: str) -> None:
        if not self.container.source_by_id(source_id):
            raise KeyError(f'Unknown source_id: {source_id}')
        if source_id not in self.readers:
            raise KeyError(f'No reader configured for source_id: {source_id}')

    def _point(self, signal_name: str) -> RegisterPoint:
        return self.container.register_map.require_point(signal_name=signal_name)

    def _reader(self, source_id: str) -> Any:
        self.validate_source_id(source_id)
        return self.readers[source_id]

    def read_value(self, source_id: str, signal_name: str) -> float:
        p = self._point(signal_name)
        return float(self._reader(source_id).read_value(p, self.container.config.decoding.byte_order))

    def write_value(self, source_id: str, signal_name: str, value: float, *, readback: bool=True) -> dict[str, Any]:
        p = self._point(signal_name)
        if int(p.rw or 0) != 1:
            raise PermissionError(f'Register {signal_name} at address {p.address} is read-only in register map')
        reader = self._reader(source_id)
        raw = reader.write_point(p, float(value))
        rb = None
        if readback:
            try:
                rb = float(reader.read_value(p, self.container.config.decoding.byte_order))
            except Exception as exc:
                rb = {'error': str(exc)}
        self.container.event_logger.info(
            'control_register_write',
            f'Wrote {signal_name}={value} to {source_id}',
            {'source_id': source_id, 'signal_name': signal_name, 'address': p.address, 'value': value, 'readback': rb, 'raw_registers': raw},
            source='control',
            asset_id=f'{source_id}_ems_system',
        )
        return {'source_id': source_id, 'signal_name': signal_name, 'address': p.address, 'value': value, 'raw_registers': raw, 'readback': rb}

    async def switch_grid_mode(self, source_id: str, target_mode: str, *, readback: bool=True, timeout_sec: float | None=None, wait_for_voltage_stable: bool=True, note: str | None=None) -> dict[str, Any]:
        command_value = 1.0 if target_mode == GRID_TIED else 2.0
        expected_status = 1.0 if target_mode == GRID_TIED else 0.0
        timeout = timeout_sec or self.container.config.control.default_timeout_sec
        result: dict[str, Any] = {
            'ok': False,
            'source_id': source_id,
            'command': 'switch_grid_mode',
            'target_mode': target_mode,
            'command_register': 164,
            'command_value': command_value,
            'note': note,
        }
        write = self.write_value(source_id, self.control_signals['grid_switch'], command_value, readback=False)
        result['write'] = write
        if readback:
            status = await self._wait_grid_status(source_id, expected_status, timeout)
            result['grid_status_check'] = status
            if not status.get('ok'):
                result['failed_step'] = 'grid_status_readback'
                self._log_control_result(result)
                return result
        if target_mode == OFF_GRID and wait_for_voltage_stable:
            stable = await self.wait_voltage_stable(source_id)
            result['voltage_stability'] = stable
            if not stable.get('ok'):
                result['failed_step'] = 'voltage_stabilization'
                self._log_control_result(result)
                return result
        result['ok'] = True
        self._log_control_result(result)
        return result

    async def _wait_grid_status(self, source_id: str, expected_status: float, timeout_sec: float) -> dict[str, Any]:
        start = time.time()
        last = None
        while time.time() - start <= timeout_sec:
            try:
                last = self.read_value(source_id, self.control_signals['grid_status'])
                if int(round(last)) == int(round(expected_status)):
                    return {'ok': True, 'expected': expected_status, 'actual': last, 'elapsed_sec': round(time.time()-start, 3)}
            except Exception as exc:
                last = {'error': str(exc)}
            await asyncio.sleep(1.0)
        return {'ok': False, 'expected': expected_status, 'actual': last, 'timeout_sec': timeout_sec}

    async def wait_voltage_stable(self, source_id: str) -> dict[str, Any]:
        cfg = self.container.config.control.voltage_stabilization
        start = time.time()
        samples: list[dict[str, float]] = []
        needed = max(2, int(max(1.0, cfg.stable_window_sec) / max(0.2, cfg.sample_interval_sec)))
        while time.time() - start <= cfg.timeout_sec:
            try:
                sample = {
                    'va': self.read_value(source_id, self.control_signals['va']),
                    'vb': self.read_value(source_id, self.control_signals['vb']),
                    'vc': self.read_value(source_id, self.control_signals['vc']),
                }
                samples.append(sample)
                samples = samples[-needed:]
                if len(samples) >= needed and self._samples_are_stable(samples, cfg):
                    return {'ok': True, 'samples': samples, 'elapsed_sec': round(time.time()-start, 3), 'tolerance_percent': cfg.tolerance_percent}
            except Exception as exc:
                samples.append({'error': str(exc)})  # type: ignore[list-item]
            await asyncio.sleep(cfg.sample_interval_sec)
        return {'ok': False, 'samples': samples[-needed:], 'timeout_sec': cfg.timeout_sec, 'tolerance_percent': cfg.tolerance_percent}

    def _samples_are_stable(self, samples: list[dict[str, float]], cfg: Any) -> bool:
        for phase in ['va', 'vb', 'vc']:
            values = [float(s[phase]) for s in samples if phase in s and isinstance(s[phase], (int, float))]
            if len(values) != len(samples):
                return False
            avg = sum(values) / len(values)
            if abs(avg) < cfg.minimum_valid_voltage:
                return False
            allowed = abs(avg) * cfg.tolerance_percent / 100.0
            if max(values) - min(values) > allowed:
                return False
        latest = samples[-1]
        vals = [float(latest[p]) for p in ['va', 'vb', 'vc']]
        avg3 = sum(vals) / 3.0
        if abs(avg3) < cfg.minimum_valid_voltage:
            return False
        imbalance = max(abs(v - avg3) for v in vals) / abs(avg3) * 100.0
        return imbalance <= cfg.phase_imbalance_tolerance_percent

    async def charge(self, source_id: str, power_kw: float, *, readback: bool=True, note: str | None=None) -> dict[str, Any]:
        if self.container.config.control.use_mode_precondition_writes:
            self._optional_precondition(source_id, mode='charge')
        write = self.write_value(source_id, self.control_signals['charge_kw'], power_kw, readback=readback)
        return self._simple_result(True, source_id, 'charge', {'power_kw': power_kw, 'write': write, 'note': note})

    async def discharge(self, source_id: str, power_kw: float, *, readback: bool=True, note: str | None=None) -> dict[str, Any]:
        if self.container.config.control.use_mode_precondition_writes:
            self._optional_precondition(source_id, mode='discharge')
        write = self.write_value(source_id, self.control_signals['discharge_kw'], power_kw, readback=readback)
        return self._simple_result(True, source_id, 'discharge', {'power_kw': power_kw, 'write': write, 'note': note})

    async def standby(self, source_id: str, *, readback: bool=True, note: str | None=None) -> dict[str, Any]:
        writes = [
            self.write_value(source_id, self.control_signals['charge_kw'], 0.0, readback=readback),
            self.write_value(source_id, self.control_signals['discharge_kw'], 0.0, readback=readback),
        ]
        if self.container.config.control.use_mode_precondition_writes:
            self._optional_precondition(source_id, mode='standby')
        return self._simple_result(True, source_id, 'standby', {'writes': writes, 'note': note})

    def _optional_precondition(self, source_id: str, *, mode: str) -> None:
        # Disabled by default. Use only if field testing shows the target power writes need these mode writes.
        optional = [
            ('remote_mode', 1.0),
            ('manual_auto_mode', 0.0),
            ('manual_mode_control', {'standby': 2.0, 'charge': 3.0, 'discharge': 4.0}.get(mode, 2.0)),
        ]
        for signal, value in optional:
            if self.container.register_map.find_point(signal_name=signal):
                self.write_value(source_id, signal, value, readback=False)

    async def switch_site_grid_mode(self, *, target_mode: str, source_ids: list[str] | None=None, source_order: list[str] | None=None, readback: bool=True, timeout_sec: float | None=None, wait_for_voltage_stable: bool=True, inter_source_delay_sec: float | None=None, note: str | None=None) -> dict[str, Any]:
        ids = source_ids or [s.source_id for s in self.container.sources]
        if target_mode == OFF_GRID:
            order = source_order or ids
            results: dict[str, Any] = {}
            for idx, sid in enumerate(order):
                res = await self.switch_grid_mode(sid, OFF_GRID, readback=readback, timeout_sec=timeout_sec, wait_for_voltage_stable=wait_for_voltage_stable, note=note)
                results[sid] = res
                if not res.get('ok'):
                    return {'ok': False, 'command': 'site_grid_mode', 'target_mode': target_mode, 'failed_source_id': sid, 'results': results}
                delay = self.container.config.control.off_grid_inter_source_delay_sec if inter_source_delay_sec is None else inter_source_delay_sec
                if delay > 0 and idx < len(order) - 1:
                    await asyncio.sleep(delay)
            return {'ok': True, 'command': 'site_grid_mode', 'target_mode': target_mode, 'execution': 'sequential', 'results': results}
        tasks = [self.switch_grid_mode(sid, GRID_TIED, readback=readback, timeout_sec=timeout_sec, wait_for_voltage_stable=False, note=note) for sid in ids]
        values = await asyncio.gather(*tasks, return_exceptions=True)
        results = {sid: (val if not isinstance(val, Exception) else {'ok': False, 'error': str(val)}) for sid, val in zip(ids, values)}
        return {'ok': all(v.get('ok') for v in results.values()), 'command': 'site_grid_mode', 'target_mode': target_mode, 'execution': 'parallel', 'results': results}

    async def site_power(self, *, operation: str, total_power_kw: float, source_ids: list[str] | None=None, allocation: str='equal', per_source_power_kw: dict[str, float] | None=None, readback: bool=True, note: str | None=None) -> dict[str, Any]:
        ids = source_ids or [s.source_id for s in self.container.sources]
        if allocation == 'custom':
            if not per_source_power_kw:
                raise ValueError('per_source_power_kw is required when allocation=custom')
            power_map = {sid: float(per_source_power_kw[sid]) for sid in ids}
        else:
            power_map = {sid: float(total_power_kw) / len(ids) for sid in ids}
        tasks = []
        for sid in ids:
            if operation == 'charge':
                tasks.append(self.charge(sid, power_map[sid], readback=readback, note=note))
            else:
                tasks.append(self.discharge(sid, power_map[sid], readback=readback, note=note))
        values = await asyncio.gather(*tasks, return_exceptions=True)
        results = {sid: (val if not isinstance(val, Exception) else {'ok': False, 'error': str(val), 'power_kw': power_map.get(sid)}) for sid, val in zip(ids, values)}
        return {'ok': all(v.get('ok') for v in results.values()), 'command': 'site_power', 'operation': operation, 'total_power_kw': total_power_kw, 'allocation': allocation, 'per_source_power_kw': power_map, 'results': results}

    async def site_standby(self, *, source_ids: list[str] | None=None, readback: bool=True, note: str | None=None) -> dict[str, Any]:
        ids = source_ids or [s.source_id for s in self.container.sources]
        values = await asyncio.gather(*[self.standby(sid, readback=readback, note=note) for sid in ids], return_exceptions=True)
        results = {sid: (val if not isinstance(val, Exception) else {'ok': False, 'error': str(val)}) for sid, val in zip(ids, values)}
        return {'ok': all(v.get('ok') for v in results.values()), 'command': 'site_standby', 'results': results}

    def _simple_result(self, ok: bool, source_id: str, command: str, extra: dict[str, Any]) -> dict[str, Any]:
        result = {'ok': ok, 'source_id': source_id, 'command': command, **extra}
        self._log_control_result(result)
        return result

    def _log_control_result(self, result: dict[str, Any]) -> None:
        sev = 'info' if result.get('ok') else 'warning'
        self.container.event_logger.log(sev, 'control_command_completed', f"Control command {result.get('command')} ok={result.get('ok')}", result, source='control', asset_id=None)
