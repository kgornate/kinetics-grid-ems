from __future__ import annotations

import struct
from enum import StrEnum


class ByteOrder(StrEnum):
    ABCD = "ABCD"  # high word first, normal bytes
    CDAB = "CDAB"  # low word first, normal bytes
    BADC = "BADC"  # high word first, byte swapped in each word
    DCBA = "DCBA"  # low word first, byte swapped in each word


class Float32Decoder:
    def __init__(self, byte_order: str = "ABCD") -> None:
        self.byte_order = ByteOrder(byte_order)

    def decode(self, registers: list[int] | tuple[int, int]) -> float:
        if len(registers) != 2:
            raise ValueError("Float32 decoding requires exactly 2 Modbus registers.")
        hi, lo = registers
        for value in (hi, lo):
            if not 0 <= int(value) <= 0xFFFF:
                raise ValueError(f"Register value out of 16-bit range: {value}")
        bytes_ab = int(hi).to_bytes(2, byteorder="big", signed=False)
        bytes_cd = int(lo).to_bytes(2, byteorder="big", signed=False)
        raw = bytes_ab + bytes_cd
        if self.byte_order == ByteOrder.ABCD:
            ordered = raw
        elif self.byte_order == ByteOrder.CDAB:
            ordered = raw[2:4] + raw[0:2]
        elif self.byte_order == ByteOrder.BADC:
            ordered = raw[1:2] + raw[0:1] + raw[3:4] + raw[2:3]
        elif self.byte_order == ByteOrder.DCBA:
            ordered = raw[::-1]
        else:
            raise ValueError(f"Unsupported byte order: {self.byte_order}")
        return struct.unpack(">f", ordered)[0]

    @staticmethod
    def encode(value: float, byte_order: str = "ABCD") -> tuple[int, int]:
        raw = struct.pack(">f", float(value))
        order = ByteOrder(byte_order)
        if order == ByteOrder.ABCD:
            ordered = raw
        elif order == ByteOrder.CDAB:
            ordered = raw[2:4] + raw[0:2]
        elif order == ByteOrder.BADC:
            ordered = raw[1:2] + raw[0:1] + raw[3:4] + raw[2:3]
        elif order == ByteOrder.DCBA:
            ordered = raw[::-1]
        else:
            raise ValueError(f"Unsupported byte order: {byte_order}")
        return int.from_bytes(ordered[0:2], "big"), int.from_bytes(ordered[2:4], "big")
