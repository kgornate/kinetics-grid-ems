"""Command-line interface for the EMS gateway."""

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="i.MX93 EMS Gateway Backend"
    )

    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run gateway in mock mode without Modbus/chiller/PCS hardware",
    )

    parser.add_argument(
        "--config-file",
        default=None,
        help=(
            "Optional JSON runtime config profile. Existing config.py and CLI "
            "arguments still work; CLI arguments override this file."
        ),
    )

    parser.add_argument(
        "--print-runtime-config",
        action="store_true",
        help="Print the merged runtime config and exit without starting services",
    )

    parser.add_argument(
        "--serial-port",
        default=None,
        help="Override Modbus serial port, example: /dev/ttyUSB1",
    )

    parser.add_argument(
        "--slave-id",
        type=int,
        default=None,
        help="Override chiller Modbus slave ID",
    )

    parser.add_argument(
        "--pc-ip",
        default=None,
        help="Override PC telemetry destination IP address",
    )

    parser.add_argument(
        "--udp-port",
        type=int,
        default=None,
        help="Override UDP telemetry destination port",
    )

    parser.add_argument(
        "--tcp-port",
        type=int,
        default=None,
        help="Override TCP command server port",
    )

    parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Override chiller Modbus polling interval in seconds",
    )

    parser.add_argument(
        "--udp-interval",
        type=float,
        default=None,
        help="Override UDP telemetry interval in seconds",
    )

    parser.add_argument(
        "--pcs-host",
        default=None,
        help="Override PCS/ModSim IP address, example: 192.168.10.1",
    )

    parser.add_argument(
        "--pcs-port",
        type=int,
        default=None,
        help="Override PCS Modbus TCP port, example: 502",
    )

    parser.add_argument(
        "--pcs-unit",
        type=int,
        default=None,
        help="Override PCS Modbus unit ID, example: 1",
    )

    parser.add_argument(
        "--pcs-vendor",
        default=None,
        help="Override PCS vendor profile, example: njoy",
    )

    parser.add_argument(
        "--pcs-poll-interval",
        type=float,
        default=None,
        help="Override PCS polling interval in seconds",
    )

    parser.add_argument(
        "--bms-host",
        default=None,
        help="Override BMS/ModSim IP address, example: 192.168.10.1",
    )

    parser.add_argument(
        "--bms-port",
        type=int,
        default=None,
        help="Override BMS Modbus TCP port, example: 502 or 1502",
    )

    parser.add_argument(
        "--bms-unit",
        type=int,
        default=None,
        help="Override BMS Modbus unit ID, example: 1",
    )

    parser.add_argument(
        "--bms-poll-interval",
        type=float,
        default=None,
        help="Override BMS polling interval in seconds",
    )

    parser.add_argument(
        "--no-chiller",
        action="store_true",
        help="Disable real chiller service",
    )

    parser.add_argument(
        "--no-pcs",
        action="store_true",
        help="Disable PCS service",
    )

    parser.add_argument(
        "--no-bms",
        action="store_true",
        help="Disable BMS service",
    )

    parser.add_argument(
        "--no-udp",
        action="store_true",
        help="Disable UDP telemetry streamer",
    )

    parser.add_argument(
        "--no-tcp",
        action="store_true",
        help="Disable TCP command server",
    )

    parser.add_argument(
        "--no-log-http",
        action="store_true",
        help="Disable HTTP log API server",
    )

    parser.add_argument(
        "--log-http-port",
        type=int,
        default=None,
        help="Override HTTP log API server port",
    )

    parser.add_argument(
        "--no-web-api",
        action="store_true",
        help="Disable EMS Web API server",
    )

    parser.add_argument(
        "--web-api-port",
        type=int,
        default=None,
        help="Override EMS Web API server port",
    )

    return parser.parse_args()
