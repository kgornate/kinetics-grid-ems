from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_BASE_DIR = "/var/lib/nb-ems-soc-solis-controller"
DEFAULT_SETTINGS_PATH = os.environ.get(
    "NB_EMS_CONTROLLER_SETTINGS_PATH",
    f"{DEFAULT_BASE_DIR}/control_settings.json",
)

DEFAULT_CONTROL_SETTINGS: dict[str, float] = {
    "derate_soc_limit": 90.0,
    "derate_power_kw": 20.0,
    "high_limit": 98.0,
    "recovery_limit": 75.0,
    "low_cutoff_limit": 10.0,
    "low_recovery_limit": 10.0,
}

SETTING_KEYS = tuple(DEFAULT_CONTROL_SETTINGS.keys())


class ControllerSettingsValidationError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_control_settings(values: dict[str, Any]) -> dict[str, float]:
    """Validate SOC thresholds and the PV derating power target.

    Existing settings files from v1.13 may contain only the four legacy thresholds.
    Missing v1.14 keys are therefore filled from DEFAULT_CONTROL_SETTINGS so an in-field
    upgrade does not break the controller or API.

    Required ordering:
        low cutoff <= low recovery <= recovery < derate SOC < high SOC <= 100
    """
    merged = dict(DEFAULT_CONTROL_SETTINGS)
    merged.update(values or {})

    normalized: dict[str, float] = {}
    for key in SETTING_KEYS:
        try:
            value = float(merged[key])
        except (TypeError, ValueError) as exc:
            raise ControllerSettingsValidationError(f"{key} must be numeric") from exc

        if key == "derate_power_kw":
            if not 0.0 < value <= 100.0:
                raise ControllerSettingsValidationError("derate_power_kw must be > 0 and <= 100 kW for this validated site")
        else:
            if not 0.0 <= value <= 100.0:
                raise ControllerSettingsValidationError(f"{key} must be between 0 and 100")
        normalized[key] = value

    low = normalized["low_cutoff_limit"]
    low_recovery = normalized["low_recovery_limit"]
    recovery = normalized["recovery_limit"]
    derate = normalized["derate_soc_limit"]
    high = normalized["high_limit"]

    if low > low_recovery:
        raise ControllerSettingsValidationError("low_cutoff_limit must be <= low_recovery_limit")
    if low_recovery > recovery:
        raise ControllerSettingsValidationError("low_recovery_limit must be <= recovery_limit")
    if recovery >= derate:
        raise ControllerSettingsValidationError("recovery_limit must be lower than derate_soc_limit")
    if derate >= high:
        raise ControllerSettingsValidationError("derate_soc_limit must be lower than high_limit")

    return normalized


class ControllerSettingsStore:
    """Persistent cross-process store for runtime SOC threshold settings.

    The FastAPI process is the writer (internal-admin only) and the standalone SOC
    controller reloads the file each cycle. Atomic replace prevents readers from
    observing a partially-written JSON file.
    """

    def __init__(self, path: str | None = None):
        self.path = Path(path or os.environ.get("NB_EMS_CONTROLLER_SETTINGS_PATH", DEFAULT_SETTINGS_PATH))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def ensure(self, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.path.exists():
            values = validate_control_settings(defaults or DEFAULT_CONTROL_SETTINGS)
            document = {
                "schema_version": 2,
                "revision": 1,
                "updated_at_utc": _utc_now(),
                "updated_by": "controller_bootstrap",
                "values": values,
            }
            self._write_document(document)
            return self._response(document)

        # Backward-compatible on-disk migration from the v1.13 four-setting schema.
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ControllerSettingsValidationError(
                f"Unable to read controller settings: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise ControllerSettingsValidationError("Controller settings file is not a JSON object")
        values_raw = raw.get("values")
        if not isinstance(values_raw, dict):
            raise ControllerSettingsValidationError("Controller settings file has no values object")

        base = dict(DEFAULT_CONTROL_SETTINGS)
        if defaults:
            base.update(defaults)
        merged = dict(base)
        merged.update(values_raw)  # Preserve all previously configured legacy values.
        values = validate_control_settings(merged)

        schema_version = int(raw.get("schema_version", 1))
        missing_keys = [key for key in SETTING_KEYS if key not in values_raw]
        if schema_version < 2 or missing_keys:
            document = {
                "schema_version": 2,
                "revision": max(1, int(raw.get("revision", 1))) + 1,
                "updated_at_utc": _utc_now(),
                "updated_by": "controller_schema_v2_migration",
                "values": values,
            }
            self._write_document(document)
            return self._response(document)

        return self.read()

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            raise FileNotFoundError(str(self.path))
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ControllerSettingsValidationError(
                f"Unable to read controller settings: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise ControllerSettingsValidationError("Controller settings file is not a JSON object")
        values_raw = raw.get("values")
        if not isinstance(values_raw, dict):
            raise ControllerSettingsValidationError("Controller settings file has no values object")
        values = validate_control_settings(values_raw)
        document = {
            "schema_version": max(1, int(raw.get("schema_version", 1))),
            "revision": max(1, int(raw.get("revision", 1))),
            "updated_at_utc": str(raw.get("updated_at_utc") or ""),
            "updated_by": str(raw.get("updated_by") or "unknown"),
            "values": values,
        }
        return self._response(document)

    def update(
        self,
        patch: dict[str, Any],
        *,
        updated_by: str,
        defaults: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        unknown = sorted(set(patch) - set(SETTING_KEYS))
        if unknown:
            raise ControllerSettingsValidationError(
                f"Unsupported controller setting(s): {', '.join(unknown)}"
            )
        if not patch:
            raise ControllerSettingsValidationError("At least one setting must be supplied")

        current = self.ensure(defaults)
        old_values = dict(current["settings"])
        merged = dict(old_values)
        merged.update(patch)
        new_values = validate_control_settings(merged)

        changes = {
            key: {"old": old_values[key], "new": new_values[key]}
            for key in SETTING_KEYS
            if old_values[key] != new_values[key]
        }

        # A no-op PATCH is valid and does not bump the revision.
        if not changes:
            response = dict(current)
            response["changed"] = False
            response["changes"] = {}
            return response

        document = {
            "schema_version": 2,
            "revision": int(current.get("revision", 1)) + 1,
            "updated_at_utc": _utc_now(),
            "updated_by": str(updated_by or "internal_admin"),
            "values": new_values,
        }
        self._write_document(document)
        response = self._response(document)
        response["changed"] = True
        response["changes"] = changes
        return response

    def _write_document(self, document: dict[str, Any]) -> None:
        payload = json.dumps(document, indent=2, sort_keys=False) + "\n"
        fd, temp_name = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            try:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            except Exception:
                pass

    def _response(self, document: dict[str, Any]) -> dict[str, Any]:
        return {
            "available": True,
            "settings_path": str(self.path),
            "schema_version": int(document.get("schema_version", 1)),
            "revision": int(document.get("revision", 1)),
            "updated_at_utc": document.get("updated_at_utc"),
            "updated_by": document.get("updated_by"),
            "settings": dict(document["values"]),
        }
