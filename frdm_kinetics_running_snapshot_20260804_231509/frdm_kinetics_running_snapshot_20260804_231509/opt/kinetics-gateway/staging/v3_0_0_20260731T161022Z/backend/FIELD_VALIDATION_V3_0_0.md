# V3.0.0 field validation checklist

Perform validation in daylight with the operator present and the physical E-stop accessible. Test one pair at a time before parallel operation.

1. Verify all PCS setpoints and actual powers are 0 kW.
2. Verify the selected PCS state is stopped and no PCS/BMS/E-stop fault is active.
3. Start the selected pair through BAU `0x3001=1` on its own BMS TCP port.
4. Verify BCU `0x0018=3`, both main contactors closed, and rack voltage matches PCS input voltage.
5. Configure and start the selected PCS at 0 kW.
6. Verify PCS reaches ready state, DC breaker feedback is closed and DC bus matches battery input.
7. Apply a low controlled charge/discharge command, then validate the requested site target.
8. Verify runtime monitoring remains healthy while other pairs are viewed or controlled.
9. Pair safe-stop: return to 0 kW, verify actual power 0, stop PCS, then BAU `0x3001=2`; verify contactors open.
10. Validate `Safe Stop All` only after individual pair safe-stop has passed.

Do not deploy or restart the backend while any pair carries non-zero power or has closed main contactors.
