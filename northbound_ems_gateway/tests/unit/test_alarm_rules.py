from nb_ems_gateway.alarms.bms_alarm_rules import evaluate_bms_alarms


def test_bms_insulation_alarm_rule():
    asset = {
        "telemetry": {
            "insulation_too_low": {"point_name": "Insulation Too Low", "value": 1}
        }
    }
    alarms = evaluate_bms_alarms(asset)
    assert alarms
