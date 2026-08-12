from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

SourceAction = Literal['manual_off', 'manual_standby']


@dataclass
class SourceSOCState:
    source_id: str
    soc: float | None = None
    quality: str | None = None
    updated_utc: str | None = None
    online: bool = False
    condition: str = 'unknown'
    last_action: str | None = None
    last_action_utc: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'source_id': self.source_id,
            'soc': self.soc,
            'quality': self.quality,
            'updated_utc': self.updated_utc,
            'online': self.online,
            'condition': self.condition,
            'last_action': self.last_action,
            'last_action_utc': self.last_action_utc,
            'last_error': self.last_error,
        }


@dataclass
class SOCProtectionStatus:
    configured_enabled: bool
    runtime_enabled: bool
    dry_run: bool
    running: bool
    solar_generation_available: bool | None
    solar_generation_kw: float | None
    last_evaluation_utc: str | None = None
    last_decision: str | None = None
    last_result: dict[str, Any] | None = None
    evaluation_count: int = 0
    command_count: int = 0
    skipped_command_count: int = 0
    source_states: dict[str, SourceSOCState] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'configured_enabled': self.configured_enabled,
            'runtime_enabled': self.runtime_enabled,
            'dry_run': self.dry_run,
            'running': self.running,
            'solar_generation_available': self.solar_generation_available,
            'solar_generation_kw': self.solar_generation_kw,
            'last_evaluation_utc': self.last_evaluation_utc,
            'last_decision': self.last_decision,
            'last_result': self.last_result,
            'evaluation_count': self.evaluation_count,
            'command_count': self.command_count,
            'skipped_command_count': self.skipped_command_count,
            'source_states': {k: v.to_dict() for k, v in self.source_states.items()},
            'history': self.history[-50:],
        }


class SOCProtectionController:
    """Automatic SOC protection controller for two independent external EMS sources.

    The controller implements the four field rules agreed with the site team:
    1. One EMS high SOC -> only that EMS Manual OFF.
    2. Both EMS high SOC -> both Manual OFF, raise solar curtailment warning if solar is available.
    3. One EMS low SOC -> only that EMS Manual OFF.
    4. Both EMS low SOC -> both Manual OFF; if solar/charging source is available, move both to Standby.

    It intentionally does not use grid-tied/off-grid switching registers. It writes only:
      manual_auto_mode = 0
      manual_mode_control = 1 or 2
    """

    def __init__(self, container: Any) -> None:
        self.container = container
        self.config = container.config.soc_protection
        self.control_service = container.control_service
        self._task: asyncio.Task | None = None
        self._running = False
        self._runtime_enabled = bool(self.config.enabled)
        self._dry_run = bool(self.config.dry_run)
        self._solar_generation_available: bool | None = self.config.solar_generation_available
        self._solar_generation_kw: float | None = None
        self._last_command: dict[str, tuple[str, float]] = {}
        self.status = SOCProtectionStatus(
            configured_enabled=bool(self.config.enabled),
            runtime_enabled=self._runtime_enabled,
            dry_run=self._dry_run,
            running=False,
            solar_generation_available=self._solar_generation_available,
            solar_generation_kw=self._solar_generation_kw,
            source_states={s.source_id: SourceSOCState(s.source_id) for s in container.sources},
        )

    async def start(self) -> None:
        if not self.config.background_enabled:
            self.container.event_logger.info(
                'soc_protection_not_started',
                'SOC protection background loop disabled by config',
                self.status.to_dict(),
                source='soc_protection',
            )
            return
        self._running = True
        self.status.running = True
        self._task = asyncio.create_task(self._loop())
        self.container.event_logger.info(
            'soc_protection_started',
            'SOC protection background loop started',
            self.status.to_dict(),
            source='soc_protection',
        )

    async def stop(self) -> None:
        self._running = False
        self.status.running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def set_runtime(self, *, enabled: bool | None = None, dry_run: bool | None = None, note: str | None = None, user: str | None = None) -> dict[str, Any]:
        if enabled is not None:
            self._runtime_enabled = bool(enabled)
            self.status.runtime_enabled = self._runtime_enabled
        if dry_run is not None:
            self._dry_run = bool(dry_run)
            self.status.dry_run = self._dry_run
        payload = {'enabled': self._runtime_enabled, 'dry_run': self._dry_run, 'note': note, 'user': user}
        self.container.event_logger.info('soc_protection_runtime_updated', 'SOC protection runtime settings updated', payload, source='soc_protection')
        return self.status.to_dict()

    def set_solar_status(self, *, available: bool | None, generation_kw: float | None = None, note: str | None = None, user: str | None = None) -> dict[str, Any]:
        self._solar_generation_available = available
        self._solar_generation_kw = generation_kw
        self.status.solar_generation_available = available
        self.status.solar_generation_kw = generation_kw
        payload = {'available': available, 'generation_kw': generation_kw, 'note': note, 'user': user}
        self.container.event_logger.info('soc_protection_solar_status_updated', 'SOC protection solar status updated', payload, source='soc_protection')
        return self.status.to_dict()

    async def _loop(self) -> None:
        while self._running:
            try:
                if self._runtime_enabled:
                    await self.evaluate_once(trigger='background')
            except Exception as exc:
                self.container.event_logger.error(
                    'soc_protection_loop_error',
                    f'SOC protection loop failed: {exc}',
                    {'error': str(exc)},
                    source='soc_protection',
                )
            await asyncio.sleep(max(1.0, float(self.config.interval_sec)))

    async def evaluate_once(self, *, trigger: str = 'manual', force: bool = False) -> dict[str, Any]:
        now = self._now()
        self.status.evaluation_count += 1
        self.status.last_evaluation_utc = now
        source_ids = [s.source_id for s in self.container.sources]
        states = {sid: self._read_source_state(sid) for sid in source_ids}
        self.status.source_states = states

        if not self.container.config.control.enabled or not self.container.config.api.commands_enabled or not self.control_service:
            return self._finish('blocked_control_disabled', {'ok': False, 'reason': 'control_or_commands_disabled', 'trigger': trigger, 'source_states': self._states_dict(states)})

        bad_sources = [sid for sid, st in states.items() if not st.online or st.soc is None or st.quality != 'good']
        if bad_sources:
            result = {'ok': False, 'reason': 'soc_not_available_or_source_offline', 'bad_sources': bad_sources, 'trigger': trigger, 'source_states': self._states_dict(states)}
            self.container.event_logger.warning('soc_protection_blocked', 'SOC protection skipped because SOC/source is not healthy', result, source='soc_protection')
            return self._finish('blocked_bad_soc_or_offline', result)

        highs = [sid for sid, st in states.items() if float(st.soc or 0.0) >= float(self.config.high_soc_limit)]
        lows = [sid for sid, st in states.items() if float(st.soc or 0.0) <= float(self.config.low_soc_limit)]
        normals = [sid for sid in source_ids if sid not in highs and sid not in lows]

        for sid, st in states.items():
            if sid in highs:
                st.condition = 'high_soc'
            elif sid in lows:
                st.condition = 'low_soc'
            else:
                st.condition = 'normal'

        actions: list[dict[str, Any]] = []
        solar = self._solar_generation_available
        decision = 'no_action'

        if len(highs) == len(source_ids) and len(source_ids) >= 2:
            decision = 'logic_2_both_high_soc'
            for sid in highs:
                actions.append(await self._manual_off(sid, reason=decision, force=force))
            if solar is True:
                self.container.event_logger.warning(
                    'soc_protection_solar_curtailment_required',
                    'Both EMS are high SOC while solar generation is available; Solis/solar curtailment is required',
                    {'source_ids': highs, 'solar_generation_available': solar, 'solar_generation_kw': self._solar_generation_kw},
                    source='soc_protection',
                )
        elif len(lows) == len(source_ids) and len(source_ids) >= 2:
            decision = 'logic_4_both_low_soc'
            for sid in lows:
                actions.append(await self._manual_off(sid, reason=decision, force=force))
            if solar is True and self.config.standby_when_both_low_and_solar_available:
                decision = 'logic_4_both_low_soc_solar_recovery_standby'
                for sid in lows:
                    actions.append(await self._manual_standby(sid, reason=decision, force=force))
            elif solar is not True:
                self.container.event_logger.warning(
                    'soc_protection_waiting_for_solar',
                    'Both EMS are low SOC; keeping both OFF while waiting for solar/charging source',
                    {'source_ids': lows, 'solar_generation_available': solar, 'solar_generation_kw': self._solar_generation_kw},
                    source='soc_protection',
                )
        elif highs and not lows:
            decision = 'logic_1_one_high_soc'
            for sid in highs:
                actions.append(await self._manual_off(sid, reason=decision, force=force))
        elif lows and not highs:
            decision = 'logic_3_one_low_soc'
            for sid in lows:
                actions.append(await self._manual_off(sid, reason=decision, force=force))
        elif highs and lows:
            # Safety extension for a possible mixed-edge case: one source too high and another too low.
            decision = 'mixed_high_low_soc_protect_each_violating_source'
            for sid in sorted(set(highs + lows)):
                actions.append(await self._manual_off(sid, reason=decision, force=force))
        else:
            decision = 'inside_safe_soc_window'

        result = {
            'ok': all(a.get('ok', False) or a.get('skipped', False) for a in actions) if actions else True,
            'trigger': trigger,
            'decision': decision,
            'high_soc_limit': self.config.high_soc_limit,
            'low_soc_limit': self.config.low_soc_limit,
            'highs': highs,
            'lows': lows,
            'normals': normals,
            'solar_generation_available': solar,
            'solar_generation_kw': self._solar_generation_kw,
            'dry_run': self._dry_run,
            'actions': actions,
            'source_states': self._states_dict(states),
        }
        severity = 'warning' if actions else 'debug'
        self.container.event_logger.log(severity, 'soc_protection_evaluated', f'SOC protection decision: {decision}', result, source='soc_protection')
        return self._finish(decision, result)

    async def _manual_off(self, source_id: str, *, reason: str, force: bool = False) -> dict[str, Any]:
        return await self._command(source_id, 'manual_off', 1.0, reason=reason, force=force)

    async def _manual_standby(self, source_id: str, *, reason: str, force: bool = False) -> dict[str, Any]:
        return await self._command(source_id, 'manual_standby', 2.0, reason=reason, force=force)

    async def _command(self, source_id: str, action: SourceAction, manual_mode_value: float, *, reason: str, force: bool) -> dict[str, Any]:
        now = time.time()
        last = self._last_command.get(source_id)
        if last and last[0] == action and not force:
            elapsed = now - last[1]
            if elapsed < float(self.config.command_cooldown_sec):
                self.status.skipped_command_count += 1
                return {'ok': True, 'skipped': True, 'source_id': source_id, 'action': action, 'reason': reason, 'cooldown_remaining_sec': round(float(self.config.command_cooldown_sec) - elapsed, 3)}

        if self._dry_run:
            self.status.command_count += 1
            self._last_command[source_id] = (action, now)
            self._update_state_action(source_id, f'dry_run_{action}', None)
            return {'ok': True, 'dry_run': True, 'source_id': source_id, 'action': action, 'reason': reason, 'writes': []}

        writes: list[dict[str, Any]] = []
        try:
            writes.append(self.control_service.write_value(source_id, 'manual_auto_mode', 0.0, readback=bool(self.config.readback)))
            writes.append(self.control_service.write_value(source_id, 'manual_mode_control', manual_mode_value, readback=bool(self.config.readback)))
            self.status.command_count += 1
            self._last_command[source_id] = (action, now)
            self._update_state_action(source_id, action, None)
            result = {'ok': True, 'source_id': source_id, 'action': action, 'reason': reason, 'writes': writes}
            self.container.event_logger.warning('soc_protection_command_sent', f'SOC protection sent {action} to {source_id}', result, source='soc_protection', asset_id=f'{source_id}_ems_system')
            return result
        except Exception as exc:
            self._update_state_action(source_id, action, str(exc))
            result = {'ok': False, 'source_id': source_id, 'action': action, 'reason': reason, 'error': str(exc), 'writes': writes}
            self.container.event_logger.error('soc_protection_command_failed', f'SOC protection failed {action} for {source_id}: {exc}', result, source='soc_protection', asset_id=f'{source_id}_ems_system')
            return result

    def _read_source_state(self, source_id: str) -> SourceSOCState:
        asset = self.container.asset_manager.snapshot(asset_id=f'{source_id}_ems_system').get(f'{source_id}_ems_system')
        if not asset:
            return SourceSOCState(source_id=source_id, online=False, condition='missing_ems_system_asset', last_error='ems_system asset not found')
        sig = (asset.get('signals') or {}).get(self.config.soc_signal_name)
        if not sig:
            # Fallback: search any asset under this source for a signal with the same name.
            for candidate in self.container.asset_manager.snapshot(source_id=source_id).values():
                maybe = (candidate.get('signals') or {}).get(self.config.soc_signal_name)
                if maybe:
                    sig = maybe
                    break
        if not sig:
            return SourceSOCState(source_id=source_id, online=bool(asset.get('online')), condition='missing_soc_signal', last_error=f'SOC signal {self.config.soc_signal_name} not found')
        value = sig.get('value')
        try:
            soc = float(value) if value is not None else None
        except Exception:
            soc = None
        return SourceSOCState(
            source_id=source_id,
            soc=soc,
            quality=sig.get('quality'),
            updated_utc=sig.get('updated_utc'),
            online=bool(asset.get('online')),
            condition='unknown',
        )

    def _update_state_action(self, source_id: str, action: str, error: str | None) -> None:
        state = self.status.source_states.setdefault(source_id, SourceSOCState(source_id))
        state.last_action = action
        state.last_action_utc = self._now()
        state.last_error = error

    def _finish(self, decision: str, result: dict[str, Any]) -> dict[str, Any]:
        self.status.last_decision = decision
        self.status.last_result = result
        entry = {'timestamp_utc': self._now(), 'decision': decision, 'result': result}
        self.status.history.append(entry)
        self.status.history = self.status.history[-100:]
        return result

    @staticmethod
    def _states_dict(states: dict[str, SourceSOCState]) -> dict[str, dict[str, Any]]:
        return {sid: st.to_dict() for sid, st in states.items()}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
