import argparse
import time

from services.storage_logger import StorageLogger


def generate_mock_chiller_data(counter: int) -> dict:
    """
    This mock data represents chiller telemetry after Modbus parsing.
    Later this dictionary will come from actual Modbus RTU readings.
    """
    return {
        "system_on_off": "ON",
        "control_mode": "AUTO",
        "set_temperature": 25.0,
        "outlet_water_temp": round(28.0 + counter * 0.1, 2),
        "return_water_temp": round(29.0 + counter * 0.1, 2),
        "outlet_water_pressure": 0.25,
        "return_water_pressure": 0.10,
        "ambient_temp": 32.0,
        "water_pump_status": "RUNNING",
        "compressor_1_status": "STOPPED",
        "compressor_2_status": "STOPPED",
        "electric_heater_status": "STOPPED",
        "condensate_fan_status": "STOPPED",
        "modbus_status": "OK",
    }


def main():
    parser = argparse.ArgumentParser(description="EMS Storage Logger Test")

    parser.add_argument(
        "--base-path",
        default="./ems_logs_test",
        help="Base path for log storage",
    )

    parser.add_argument(
        "--samples",
        type=int,
        default=10,
        help="Number of telemetry samples to log",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Delay between samples in seconds",
    )

    args = parser.parse_args()

    logger = StorageLogger(
        base_path=args.base_path,
        gateway_id="imx93_gateway_1",
        asset_id="chiller_1",
    )

    print("====================================================")
    print("        EMS Storage Logger Test")
    print("====================================================")
    print(f"Base Path : {args.base_path}")
    print(f"Samples   : {args.samples}")
    print(f"Interval  : {args.interval} sec")
    print("====================================================")

    print("[TEST] Initializing logger...")
    init_status = logger.initialize()

    if not init_status:
        print("[TEST] Logger initialization failed")
        print("[TEST] Status:", logger.get_status())
        return

    print("[TEST] Logger initialized successfully")
    print("[TEST] Status:", logger.get_status())

    logger.log_event(
        event_type="LOGGER_TEST_STARTED",
        source="test_storage_logger.py",
        status="success",
        description="Storage logger test started",
    )

    for i in range(args.samples):
        telemetry = generate_mock_chiller_data(i)
        log_status = logger.log_telemetry(telemetry)

        if log_status:
            print(f"[TEST] Telemetry sample {i + 1}/{args.samples} logged")
        else:
            print(f"[TEST] Telemetry sample {i + 1}/{args.samples} failed")

        time.sleep(args.interval)

    logger.log_event(
        event_type="LOGGER_TEST_COMPLETED",
        source="test_storage_logger.py",
        status="success",
        description="Storage logger test completed",
    )

    print("[TEST] Final logger status:", logger.get_status())
    print("[TEST] Logger test completed")


if __name__ == "__main__":
    main()