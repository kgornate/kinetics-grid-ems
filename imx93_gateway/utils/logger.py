"""
Simple logger utility for i.MX93 EMS Gateway.

Currently the project mainly uses print() statements.
This file is added so later we can shift to proper logging
without changing the whole codebase.
"""

import logging


def get_logger(name: str = "ems_gateway") -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger