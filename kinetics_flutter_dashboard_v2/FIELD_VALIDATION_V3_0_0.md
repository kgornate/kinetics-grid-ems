# Flutter V3.0.0 hardware validation

1. Log in as Internal and verify all four pair cards appear.
2. Verify each card updates while another pair is starting or carrying power.
3. For each pair, run automatic ramp at a low target and confirm BAU precharge, PCS startup and signed power.
4. Confirm negative power is displayed as charging and positive power as discharging.
5. Change one running pair with `Set power directly`; verify other pair cards remain responsive.
6. Use pair safe shutdown and verify only the selected pair reaches 0 kW/stopped/contactors open.
7. After individual checks, test `Safe stop all pairs` and inspect each pair result in Latest gateway response.
8. Disconnect/reconnect REST/WebSocket and verify the dashboard hydrates from compact REST then resumes delta telemetry.
9. Confirm stale/cache labels are visible and no screen launches repeated live-hardware reads.
