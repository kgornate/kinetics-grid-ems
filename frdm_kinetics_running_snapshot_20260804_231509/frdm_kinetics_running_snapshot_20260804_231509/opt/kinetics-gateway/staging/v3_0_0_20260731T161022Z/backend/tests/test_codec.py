from app.protocols.codec import decode_point, encode_scalar, validate_value


def test_signed_32_big_endian_decode():
    point = {"data_type": "S32", "register_width": 2, "element_count": 1, "scale": 0.1, "bitfields": []}
    encoded = encode_scalar(-123.4, "S32", scale=0.1)
    decoded = decode_point(point, encoded)
    assert round(decoded["value"], 1) == -123.4


def test_bitfield_decode():
    point = {
        "data_type": "U16", "register_width": 1, "element_count": 1, "scale": None,
        "bitfields": [{"bit": 2, "key": "fault"}, {"bit": 5, "key": "alarm"}],
    }
    decoded = decode_point(point, [0b100100])
    assert decoded["bitfields"] == {"fault": 1, "alarm": 1}


def test_range_validation():
    point = {"key": "setpoint", "range_text": "[-10~10]"}
    validate_value(point, 5)
    try:
        validate_value(point, 20)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected range validation error")
