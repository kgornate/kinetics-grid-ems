# Register Map and Normalization

The generated register map is stored at:

```text
data/register_maps/china_ems_northbound_v1.json
```

The manual dashboard-grade normalization overlay is stored at:

```text
data/normalization/curated_signal_map.json
```

The full map remains read-only. The curated layer only changes software-facing names, categories, display names, key-signal flags, and enum mappings. It does not enable writes.

## Normalization concept

Raw vendor points are converted into internal signal names that are stable for dashboard/API use.

Examples:

```text
Address 1532, Display SOC
→ bms_1.soc.display_percent

Address 1552, Cluster Total Voltage (Acquired)
→ bms_1.dc.cluster_voltage_v

Address 1928, Total Active Power
→ pcs_1.ac.total_active_power_kw

Address 2002, Insulation Resistance Value
→ pcs_1.insulation.resistance

Address 2462, Fire Alarm
→ fire_protection.status.fire_alarm
```

## Current curated status

The map currently includes 155 manually curated key/dashboard signals and heuristic categories for all 1,421 points. Cell voltages and battery temperatures are also grouped into `battery_cells` dashboard groups.
