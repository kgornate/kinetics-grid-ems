KINETICS GATEWAY V2.5.1 PATCH

Purpose:
- Apply the individual-rack BCU control findings from Pair 4 commissioning.
- Remove normal-runtime writes to BAU 0x3005-0x3008.
- Use each selected rack's own BCU 0x0402 command for Rack 1-4.
- Correct pair-level BMS direction-permission logic.

Install on FRDM:

  cd /tmp/kinetics_gateway_v2_5_1_individual_rack_bcu_patch
  sh deployment/update_individual_rack_bcu_control_v2_5_1_on_imx93.sh

The installer:
- creates a timestamped backup;
- preserves /etc/kinetics-gateway/config.json;
- sends no BMS or PCS hardware command;
- restarts kinetics-gateway.service;
- retains the current automatic-enable setting and timeout values.

After installation, first test Pair 4 at zero power and then a conservative 20 kW discharge. Keep the E-stop accessible and validate one pair at a time.
