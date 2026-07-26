# Kinetics Gateway Data-Rate and Storage Analysis

This analysis is generated from the complete mock plant using the current protocol catalogs:

- BMS bank/BAU: 155 active points
- Four racks/BCUs: 371 active points per rack
- Power/environment: 131 active points across logical assets
- PCS: 230 points
- Total logical assets stored: 13
- Full bulk arrays: included in the cached telemetry state

The values below are application-level estimates. Actual field usage can vary because of JSON values, active alarms, retransmissions, TLS/Cloudflare overhead, connected-client count and the actual number of populated cells/sensors.

## 1. Multi-rate polling schedule

| Group | Interval | Purpose |
|---|---:|---|
| BMS fast | 1 s | Bank/rack live electrical values, operating states and critical status |
| BMS normal | 5 s | Rack measurements, environment, HVAC, cooling, meters and normal alarms |
| BMS slow | 60 s | Versions, counters, settings and slow-changing parameters |
| BMS bulk | 30 s | Complete cell-voltage and temperature arrays for all four racks |
| PCS | 5 s | All 230 PCS registers; currently raw until vendor decoding is loaded |

Every group runs in its own background task. The latest values from every group are merged into one complete cached plant snapshot.

## 2. Field-side Modbus TCP load

The Modbus client now keeps persistent TCP connections and reconnects automatically after a transport failure.

| Group | Requests/cycle | Registers/cycle | Estimated wire data/minute |
|---|---:|---:|---:|
| BMS fast | 10 | 230 | 105,000 bytes |
| BMS normal | 16 | 618 | 39,600 bytes |
| BMS slow | 25 | 1,134 | 5,493 bytes |
| BMS bulk | 24 | 6,144 | 30,768 bytes |
| PCS | 2 | 230 | 8,616 bytes |
| **Total** | — | **37,398 registers/minute** | **189,477 bytes/minute** |

Estimated average field Ethernet load:

- Approximately **3.16 kB/s**
- Approximately **25.3 kbit/s**
- Approximately **0.19 MB/minute**

This is a very small load for 100 Mbps or 1 Gbps Ethernet. The main commissioning concern is therefore not bandwidth; it is whether the BAU accepts the planned polling rate and all requested register blocks reliably.

## 3. Data sent to Flutter/server

The recommended WebSocket mode is now:

1. One complete compact snapshot when the client connects.
2. Multi-rate delta messages afterward.

Static register metadata such as names, addresses, access and definitions is available through the protocol-catalog APIs and is not repeated in every telemetry message.

### Initial connection

- Compact complete snapshot: approximately **150,163 bytes** or **0.15 MB**
- Full debug snapshot with repeated metadata: approximately **571,678 bytes** or **0.57 MB**

### Continuous delta stream for one connected client

| Group | Event size | Events/minute | Data/minute |
|---|---:|---:|---:|
| BMS fast | 28,323 bytes | 60 | 1.699 MB |
| BMS normal | 29,790 bytes | 12 | 0.357 MB |
| BMS slow | 54,417 bytes | 1 | 0.054 MB |
| BMS bulk | 32,388 bytes | 2 | 0.065 MB |
| PCS | 7,549 bytes | 12 | 0.091 MB |
| **Total** | — | — | **2.267 MB/minute** |

Estimated continuous streaming rate for one client:

- Approximately **37.8 kB/s**
- Approximately **302 kbit/s** application payload
- Allow approximately **0.35–0.40 Mbps** after WebSocket, TLS and Cloudflare overhead
- Approximately **3.26 GB/day** if one client remains connected continuously for 24 hours

Each additional continuously connected client approximately multiplies the outbound traffic. A local Flutter client connected only while in use will consume much less daily traffic.

The legacy `mode=full` WebSocket option sends the complete debug snapshot repeatedly and is not recommended for normal operation because it can approach approximately **4.6 Mbps** at one snapshot per second.

## 4. SQLite historian storage

Historian policy:

- Complete merged plant state stored every 5 seconds
- 13 asset rows per complete sample
- Compact value/quality/bitfield representation
- Static metadata excluded from every history row
- JSON compressed with zlib and stored as SQLite BLOB
- SQLite WAL mode
- Alarms, alarm transitions, events and command audit stored separately

Measured complete mock sample:

- Uncompressed: approximately **149,030 bytes**
- Compressed: approximately **16,529 bytes**
- Compression ratio: approximately **11.1%**

Estimated historian growth:

- Approximately **285.6 MB/day**
- Approximately **0.266 GiB/day**
- Approximately **8.0 GiB per 30 days**

For the configured 25 GiB application quota:

- Full theoretical quota: approximately **94 days**
- Automatic 90% high-watermark: approximately **84.6 days**
- The configured 90-day age retention and quota enforcement work together; the quota high-watermark will normally remove the oldest telemetry first at around 84 days with this data profile.

Actual retention will be slightly lower if runtime logs, WAL files, large alarm histories or unusually large JSON values grow significantly. The storage status API reports real usage continuously.

## 5. Storage paths and protection

Preferred production path:

```text
/mnt/ems-logs/kinetics-gateway
```

Expected mount point:

```text
/mnt/ems-logs
```

Hardware configuration requires the mount point to be present before the preferred SD path is selected. Otherwise, the software uses its configured local fallback and reports this through:

```text
GET /api/storage/status
```

The application quota is 25 GiB with a 90% high-watermark. Oldest telemetry is removed in batches when the high-watermark is crossed.

## 6. Runtime measurement API

Use this endpoint after real hardware is connected:

```text
GET /api/diagnostics/data-rate
```

It reports:

- Polling intervals
- Actual observed event sizes
- Estimated Modbus load
- Estimated WebSocket data rate
- Current compressed historian sample size
- Estimated daily storage growth
- Estimated days remaining within the configured quota

The estimates should be checked again after the first real BAU/PCS extraction because actual populated arrays and vendor values may change compression and payload sizes.
