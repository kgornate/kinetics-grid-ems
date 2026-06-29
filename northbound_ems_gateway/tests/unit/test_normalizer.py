from nb_ems_gateway.normalization.signal_name_mapper import normalize_signal_name


def test_normalize_signal_name():
    assert normalize_signal_name("bms_1", "Cluster Total Voltage", "V") == "bms_1.cluster_total_voltage_v"
