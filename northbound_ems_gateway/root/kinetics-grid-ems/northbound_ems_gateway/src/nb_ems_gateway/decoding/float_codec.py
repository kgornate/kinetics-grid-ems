import struct

def decode_float32(registers: list[int], byte_order: str='ABCD') -> float:
    a=registers[0].to_bytes(2,'big'); b=registers[1].to_bytes(2,'big'); raw=a+b
    if byte_order=='ABCD': data=raw
    elif byte_order=='CDAB': data=b+a
    elif byte_order=='BADC': data=bytes([raw[1],raw[0],raw[3],raw[2]])
    elif byte_order=='DCBA': data=raw[::-1]
    else: raise ValueError(byte_order)
    return struct.unpack('>f',data)[0]

def encode_float32(value: float, byte_order: str='ABCD') -> list[int]:
    raw=struct.pack('>f',float(value))
    if byte_order=='ABCD': data=raw
    elif byte_order=='CDAB': data=raw[2:]+raw[:2]
    elif byte_order=='BADC': data=bytes([raw[1],raw[0],raw[3],raw[2]])
    elif byte_order=='DCBA': data=raw[::-1]
    else: raise ValueError(byte_order)
    return [int.from_bytes(data[:2],'big'),int.from_bytes(data[2:],'big')]
