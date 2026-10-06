from __future__ import annotations

from typing import Callable, Any

from app.assets.bms_driver import BmsModbusDriver
from app.assets.pcs_driver import PcsModbusDriver
from app.assets.mock_control_drivers import MockBmsControlDriver, MockPcsControlDriver
from app.assets.mock_plant import MockPlant
from app.core.config import GatewayConfig
from app.services.bms_pcs_control import BmsPcsControlService
from app.services.vendor_neutral_control import VendorNeutralPairControlService
from app.storage.sqlite_store import SQLiteStore


def build_pair_control_service(
    config: GatewayConfig,
    bms_driver: BmsModbusDriver,
    pcs_driver: PcsModbusDriver,
    store: SQLiteStore,
    *,
    snapshot_provider: Callable[[int, str], dict[str, Any]] | None = None,
    mock_plant: MockPlant | None = None,
):
    """Select the pair controller without changing the public API contract.

    Kinetics remains on the field-validated legacy controller.  The new
    Lineage+Elecod combination uses the vendor-neutral adapter-driven controller.
    Future vendor combinations can be added here without changing REST routes,
    historian, alarm engine or application code.
    """

    bms_vendor = config.bms.vendor.strip().lower()
    pcs_vendor = config.pcs.vendor.strip().lower()
    if bms_vendor == "lineage" and pcs_vendor == "elecod":
        if config.mode == "mock" and mock_plant is not None:
            bms_driver = MockBmsControlDriver(config.bms, bms_driver.catalog, mock_plant)  # type: ignore[assignment]
            pcs_driver = MockPcsControlDriver(config.pcs, pcs_driver.catalog, mock_plant)  # type: ignore[assignment]
        return VendorNeutralPairControlService(
            config,
            bms_driver,  # type: ignore[arg-type]
            pcs_driver,  # type: ignore[arg-type]
            store,
            snapshot_provider=snapshot_provider,
        )
    return BmsPcsControlService(
        config,
        bms_driver,
        pcs_driver,
        store,
        snapshot_provider=snapshot_provider,
    )
