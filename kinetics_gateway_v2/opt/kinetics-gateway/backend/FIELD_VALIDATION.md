# Field validation sequence

Do not begin with a four-pair high-power test.

1. Confirm all four pairs are online, stopped, at 0 kW, and free of read errors.
2. Start Pair 4 at 2 kW discharge and wait until its runtime monitor is active.
3. Start Pair 3 at 2 kW and confirm Pair 4 remains near 2 kW.
4. Start Pair 2 at 2 kW and confirm Pairs 3 and 4 remain active.
5. Start Pair 1 at 2 kW and confirm all four remain active.
6. Inspect `/api/control-sequence/status/all` and
   `/api/diagnostics/runtime-monitor`.
7. Confirm no audit/event entry reports safe-stop caused only by
   `global_refresh_lane_busy`.
8. Safe-stop one pair and verify the other three continue.
9. Safe-stop all pairs and verify 0 kW and open BMS contactors.
10. Repeat at 10 kW only after the 2 kW validation is clean.

At every stage, stop testing for real BMS/PCS faults, open contactors, invalid
current limits, communication loss beyond the grace period, or unexpected power.
