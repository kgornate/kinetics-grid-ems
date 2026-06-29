from nb_ems_gateway.decoding.float32_decoder import Float32Decoder


def test_float_round_trip_abcd():
    regs = Float32Decoder.encode(62.5, "ABCD")
    assert Float32Decoder("ABCD").decode(regs) == 62.5


def test_float_round_trip_cdab():
    regs = Float32Decoder.encode(50.0, "CDAB")
    assert Float32Decoder("CDAB").decode(regs) == 50.0
