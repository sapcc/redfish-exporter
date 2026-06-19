# Redfish Exporter — Metrics Reference

This document provides a comprehensive reference for all Prometheus metrics exported by the redfish-exporter. Metrics are grouped by the HTTP endpoint that produces them.

---

## Common Labels

All metrics include the following base labels unless noted otherwise.

| Label | Description |
|---|---|
| `host` | Hostname or IP address of the target BMC |
| `server_manufacturer` | Hardware manufacturer (e.g. `Dell`, `HPE`, `Cisco`, `Lenovo`) |
| `server_model` | Server model string (e.g. `PowerEdge R740`) |
| `server_serial` | Serial number of the **server** (from the Redfish API) |

### The `serial` label

Component-level metrics additionally carry a `serial` label that holds the **individual component's serial number** as reported by the Redfish API (the `SerialNumber` field of the respective resource). It is set to `n/a` when the field is absent or empty.

`serial` is intentionally distinct from `server_serial`: `server_serial` identifies the physical server, while `serial` identifies the specific component (disk, NIC, DIMM, PSU, etc.).

> **Vendor reality:** Many vendors (notably HPE) do not populate `SerialNumber` on every Redfish resource — particularly on entries in `UpdateService/FirmwareInventory`. In those cases `serial` is `n/a`.

### The `id` label

Multi-instance components (PSUs, fans, DIMMs, disks, processors, storage controllers, firmware items) also carry an `id` label that holds the resource's `Id` field (or `MemberId` for entries embedded in arrays such as the legacy `Power.PowerSupplies`/`Thermal.Fans`).

`id` exists primarily to **guarantee a unique time series per component**, regardless of whether the vendor exposes a serial number. Without it, two PSUs of the same model on the same server would collapse to one Prometheus series and one of the readings would be silently dropped on ingestion.

For firmware items the same purpose is served by the `item_id` label.

---

## `/health` endpoint

Scrapes general system health, power state, memory error counters, and TLS certificate validity.

### `redfish_up`

Indicates whether the Redfish API responded successfully.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host` |
| **Values** | `1` — API reachable and responding; `0` — unreachable or error |

> **Note:** This metric is emitted before the full server identity (manufacturer, model, serial) is known, so it carries only the `host` label.

---

### `redfish_version`

Reports the Redfish protocol version supported by the BMC. The version string is carried as a label; the metric value is always `1`.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial`, `version` |
| **Values** | Always `1` (info metric) |
| **Source** | `GET /redfish/v1` → `RedfishVersion` |

---

### `redfish_response_duration_seconds`

Round-trip duration of the initial unauthenticated request to `/redfish/v1`, in seconds.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host` |
| **Unit** | Seconds |

---

### `redfish_powerstate`

Current power state of the server.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial` |
| **Values** | `1` — powered on; `0` — powered off |
| **Source** | `GET /redfish/v1/Systems/{id}` → `PowerState` |

---

### `redfish_health`

Health status of individual hardware components. A single metric family with a `device_type` label selects the component category; additional labels carry component-specific details.

| | |
|---|---|
| **Type** | Gauge |
| **Values** | `0` — OK / Operable; `1` — Critical / Error; `2` — Warning |
| **Source** | Multiple Redfish endpoints (see per-device table below) |

#### Health value encoding

| Redfish status string | Metric value |
|---|---|
| `OK`, `Operable`, `Enabled`, `Good` | `0` |
| `Critical`, `Error` | `1` |
| `Warning` | `2` |
| `Absent` or missing | not emitted |

#### Per-device labels

**System summary** — overall system health roll-up

| Label | Value |
|---|---|
| `device_type` | `system` |
| `device_name` | `summary` |
| `id` | `summary` |
| `serial` | `n/a` |
| **Source** | `GET /redfish/v1/Systems/{id}` → `Status.Health` |

**Processor**

| Label | Description |
|---|---|
| `device_type` | `processor` |
| `device_name` | Socket identifier (e.g. `CPU1`) |
| `device_manufacturer` | CPU manufacturer |
| `cpu_type` | Processor type (e.g. `Central Processor`) |
| `cpu_model` | CPU model string |
| `cpu_cores` | Total number of cores |
| `cpu_threads` | Total number of threads |
| `id` | Redfish `Id` (always present, unique within the collection) |
| `serial` | CPU serial number; `n/a` if not provided |
| **Source** | `GET /redfish/v1/Systems/{id}/Processors/{id}` |

**Storage controller**

| Label | Description |
|---|---|
| `device_type` | `storage` |
| `device_name` | Controller name |
| `device_manufacturer` | Controller manufacturer |
| `controller_model` | Controller model string |
| `id` | Redfish `Id` |
| `serial` | Controller serial number; `n/a` if not provided |
| **Source** | `GET /redfish/v1/Systems/{id}/Storage/{id}` → `StorageControllers[0]` |

**Disk**

| Label | Description |
|---|---|
| `device_type` | `disk` |
| `device_name` | Drive name |
| `disk_type` | Media type (e.g. `SSD`, `HDD`) |
| `device_manufacturer` | Drive manufacturer |
| `disk_model` | Drive model |
| `disk_capacity` | Capacity in bytes |
| `disk_protocol` | Interface protocol (e.g. `SAS`, `NVMe`) |
| `id` | Redfish `Id` |
| `serial` | Drive serial number; `n/a` if not provided |
| **Source** | `GET /redfish/v1/Systems/{id}/Storage/{id}/Drives/{id}` |

**Chassis**

| Label | Description |
|---|---|
| `device_type` | `chassis` |
| `device_name` | Chassis name |
| `id` | Redfish `Id` |
| `serial` | Chassis serial number; `n/a` if not provided |
| **Source** | `GET /redfish/v1/Chassis/{id}` |

**Power supply**

| Label | Description |
|---|---|
| `device_type` | `powersupply` |
| `device_name` | PSU name |
| `device_model` | PSU model |
| `id` | Redfish `MemberId` (or `Id` if exposed) |
| `serial` | PSU serial number; `n/a` if not provided |
| **Source** | `GET /redfish/v1/Chassis/{id}/Power` → `PowerSupplies[]` |

**Fan**

| Label | Description |
|---|---|
| `device_type` | `fan` |
| `device_name` | Fan name |
| `id` | Redfish `MemberId` (or `Id` if exposed) |
| `serial` | Fan serial number; `n/a` if not provided |
| **Source** | `GET /redfish/v1/Chassis/{id}/Thermal` → `Fans[]` |

**Memory (DIMM)**

| Label | Description |
|---|---|
| `device_type` | `memory` |
| `device_name` | DIMM slot name (e.g. `DIMM_A1`) |
| `dimm_capacity` | Capacity in MiB |
| `dimm_speed` | Operating speed in MHz |
| `dimm_type` | Memory device type (e.g. `DDR4`) |
| `device_manufacturer` | DIMM manufacturer |
| `id` | Redfish `Id` |
| `serial` | DIMM serial number; `n/a` if not provided |
| **Source** | `GET /redfish/v1/Systems/{id}/Memory/{id}` |

**Network adapter (NIC)**

| Label | Description |
|---|---|
| `device_type` | `nic` |
| `device_name` | Adapter name |
| `device_manufacturer` | NIC manufacturer |
| `device_model` | NIC model string |
| `id` | Redfish `Id` |
| `serial` | NIC card serial number; `n/a` if not provided |
| `port_speed_gbps` | Maximum port speed across all ports in Gbps (e.g. `100`); `unknown` if not determinable |
| **Source** | `GET /redfish/v1/Chassis/{id}/NetworkAdapters/{id}` — port speed from `NetworkPorts` (most vendors) or `Ports` (HPE Gen11) |

---

### `redfish_memory_correctable`

Count of correctable ECC errors per DIMM slot.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | Same as `redfish_health` for `device_type=memory` |
| **Values** | Error count (integer ≥ 0) |
| **Source** | `GET /redfish/v1/Systems/{id}/Memory/{id}/Metrics` → `HealthData.AlarmTrips.CorrectableECCError` |

> **Vendor notes:** Cisco servers do not expose this value via the Redfish API. Dell PowerEdge servers report it only for selected DIMM manufacturers (Micron Technology and Hynix Semiconductor — not Samsung).

---

### `redfish_memory_uncorrectable`

Count of uncorrectable ECC errors per DIMM slot.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | Same as `redfish_health` for `device_type=memory` |
| **Values** | Error count (integer ≥ 0) |
| **Source** | `GET /redfish/v1/Systems/{id}/Memory/{id}/Metrics` → `HealthData.AlarmTrips.UncorrectableECCError` |

---

### `redfish_certificate_isvalid`

Whether the BMC's TLS certificate is currently valid (not expired and hostname matches).

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial`, `issuer`, `subject`, `not_after` |
| **Values** | `1` — valid; `0` — invalid or unretrievable |
| **Source** | TLS handshake against port 443 of the target host |

---

### `redfish_certificate_valid_hostname`

Whether the certificate's Common Name (CN) matches the target hostname.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial`, `issuer`, `subject`, `not_after` |
| **Values** | `1` — hostname matches CN; `0` — mismatch |

---

### `redfish_certificate_valid_days`

Number of days remaining until certificate expiry. Negative values indicate an already-expired certificate.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial`, `issuer`, `subject`, `not_after` |
| **Unit** | Days |

---

### `redfish_certificate_selfsigned`

Whether the BMC's TLS certificate is self-signed (issuer equals subject).

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial`, `issuer`, `subject`, `not_after` |
| **Values** | `1` — self-signed; `0` — issued by a CA |

---

### `redfish_health_scrape_duration_seconds`

Total time taken to scrape all health-endpoint metrics for one target.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial` |
| **Unit** | Seconds |

---

## `/firmware` endpoint

Scrapes the firmware inventory of the server.

### `redfish_firmware`

Info metric representing one installed firmware component. The version and component identity are carried in labels; the metric value is always `1`.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial`, `item_name`, `item_id`, `item_manufacturer`, `serial`, `version` |
| **Values** | Always `1` |
| **Source** | `GET /redfish/v1/UpdateService/FirmwareInventory/{id}` |

The `item_id` label holds the Redfish `Id` of the firmware inventory entry. It is required to keep series distinct when several components share the same `item_name` (e.g. two PSUs of the same type, four backplane firmwares — common on HPE).

The `serial` label holds the firmware component's own serial number (`SerialNumber` field). It is set to `n/a` when the field is absent or empty — it is never populated with the server serial number. In practice many vendors (notably HPE) do not populate `SerialNumber` on firmware inventory entries; rely on `item_id` for uniqueness in that case.

> **Vendor notes:** On Dell PowerEdge servers only entries whose URL contains `Installed` are included, filtering out pending or staged firmware. On Lenovo servers the `Firmware:` prefix is stripped from component names.

---

### `redfish_firmware_scrape_duration_seconds`

Total time taken to scrape all firmware-endpoint metrics for one target.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial` |
| **Unit** | Seconds |

---

## `/performance` endpoint

Scrapes power consumption and temperature data.

### `redfish_power`

Power reading for a component. The `type` label identifies the specific measurement; additional labels identify the power supply unit when applicable.

| | |
|---|---|
| **Type** | Gauge |
| **Unit** | Watts |
| **Source** | `GET /redfish/v1/Chassis/{id}/PowerSubsystem` (preferred) or `GET /redfish/v1/Chassis/{id}/Power` (legacy fallback) |

#### Modern PowerSubsystem path (Redfish 2023+)

**Subsystem-level readings** (from `PowerSubsystem` resource):

| `type` label value | Description |
|---|---|
| `CapacityWatts` | Total power capacity of the subsystem |
| `RequestedWatts` | Requested power allocation |
| `AllocatedWatts` | Currently allocated power |

**Chassis-level reading** (from the legacy `Chassis/{id}/Power` resource — always read when available):

| Label | Description |
|---|---|
| `type` | `PowerConsumedWatts` |
| `id` | `MemberId` (or `Id`) of the `PowerControl[]` entry — usually `0` for a single chassis |

This series is the chassis-wide instantaneous power consumption. On HPE iLO 6 it is the only reliably non-stale power figure available because the modern `PowerSupplies/{id}/Metrics` readings are often frozen at `0.0` even on populated and operational PSUs.

**Per-PSU readings** (from `PowerSupplies/{id}/Metrics`):

| Label | Description |
|---|---|
| `type` | Measurement type: `PowerInputWatts`, `PowerOutputWatts`, `PowerCapacityWatts`, `InputPowerWatts`, or `OutputPowerWatts` |
| `Name` | PSU name |
| `Manufacturer` | PSU manufacturer |
| `Model` | PSU model |
| `id` | Redfish `Id` of the PSU resource |
| `serial` | PSU serial number; `n/a` if not provided |

> **Notes:**
> - Per-metric readings are taken from the `PowerSupplies/{id}/Metrics` sub-resource when present; otherwise the exporter falls back to the same field on the parent `PowerSupplies/{id}` resource. Only metrics that exist on at least one of the two resources are emitted.
> - **PSUs whose every reading is zero or missing are silently dropped** — they contribute no useful information and would only clutter dashboards. Empty bays and BMC-broken bays both fall under this rule. The chassis-level `PowerConsumedWatts` aggregate above remains available regardless.
> - PSU bays reporting `Status.State = "Absent"` are **not** filtered on that field alone. Some vendor BMCs (notably HPE iLO 6) mark every bay as `Absent` on the modern `PowerSubsystem` resource even when the PSU is physically present and operational. The all-zero-readings rule above handles both real and falsely-reported absence in a single check.
> - When the modern `PowerSubsystem` resource yields no readings at all, the exporter falls back to the deprecated `Chassis/{id}/Power` resource (see *Legacy Power path* below).

#### Legacy Power path (deprecated, fallback only)

**Per-PSU readings** (from `Power.PowerSupplies[]`):

| Label | Description |
|---|---|
| `type` | Measurement type: `PowerOutputWatts`, `PowerInputWatts`, `LineInputVoltage`, or `EfficiencyPercent` |
| `device_name` | PSU name |
| `device_model` | PSU model |
| `id` | Redfish `MemberId` (or `Id` if exposed) |
| `serial` | PSU serial number; `n/a` if not provided |

#### Vendor coverage matrix for `redfish_power`

Different BMC firmware families populate the Redfish power resources very differently. The exporter publishes whatever each one actually exposes — empty/zero readings are dropped rather than reported as misleading zeros. The table below captures the patterns observed in production:

| Vendor / firmware | Subsystem aggregate (`CapacityWatts`, `RequestedWatts`, `AllocatedWatts`) | Per-PSU live readings (`InputPowerWatts`, `OutputPowerWatts`) | Per-PSU `PowerCapacityWatts` | Chassis-level `PowerConsumedWatts` |
|---|---|---|---|---|
| **Dell** iDRAC 9 (PowerEdge R860 and similar) | All three | Real values per PSU | Real value per PSU | One series per chassis |
| **Lenovo** XCC (ThinkSystem SR650 V3 and similar) | All three | Not exposed on the modern resource | Real value per PSU (static) | Multiple series — one per `PowerControl[]` domain (often 3) |
| **HPE** iLO 6 (ProLiant Gen11) | `CapacityWatts` only | Reported as `0.0` (firmware bug) — dropped | Reported as `0` — dropped | One series per chassis (the only reliable HPE Gen11 wattage) |
| **HPE** iLO 5 (ProLiant Gen10) | Not present | — | — | Falls back to *Legacy Power path* per-PSU readings |
| **Cisco** UCS (C220/C240 series, BMC FW ≥ 4.x) | Not exposed | Not exposed on the modern resource | — | Falls back to *Legacy Power path* per-PSU readings |
| **Fujitsu** iRMC (PRIMERGY RX2540 M8 and similar) | Not present | Not exposed at standard Redfish paths | Real value per PSU (via legacy path) | Not exposed at standard Redfish paths |

> Dropped means: the silent-PSU rule above suppresses series whose every reading is zero or missing, so HPE Gen11 emits no per-PSU `redfish_power` series and instead surfaces consumption only through the chassis-level aggregate. This is intentional — it keeps dashboards uncluttered while preserving the only number the BMC reports honestly.

---

### `redfish_temperature_Celsius`

Temperature readings summarised at the chassis level.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial`, `type` |
| **Unit** | Degrees Celsius |
| **Source** | `GET /redfish/v1/Chassis/{id}/ThermalSubsystem/ThermalMetrics` → `TemperatureSummaryCelsius` |

The `type` label reflects the Redfish key name from `TemperatureSummaryCelsius`, for example:

| `type` value | Description |
|---|---|
| `Ambient` | Ambient (room) temperature |
| `Inlet` | Chassis inlet air temperature |
| `Exhaust` | Chassis exhaust air temperature |
| `Internal` | Internal chassis temperature |

> **Note:** Available keys depend on the server model and BMC firmware version.

#### Legacy Thermal path (fallback for vendors without `ThermalSubsystem`)

When the modern `ThermalSubsystem` resource is missing or yields no readings, the exporter falls back to the deprecated `Chassis/{id}/Thermal` resource and emits one series per entry of its `Temperatures[]` array. This path is used by vendors such as Fujitsu iRMC and older HPE iLO 5 firmware.

| Label | Description |
|---|---|
| `type` | Sensor `Name` from the array entry (e.g. `CPU1`, `MB_Outlet`, `PSU1_Inlet`) |
| `id` | Redfish `MemberId` (or `Id`) of the array entry |
| `host`, `server_*` | Standard host/server labels |

Sensors whose `Status.State == "Absent"` are skipped, and entries without a `ReadingCelsius` value are not emitted. The number of emitted series therefore varies widely across vendors: Fujitsu PRIMERGY publishes ~20 active sensors per server (CPU dies, DIMM banks, PSU intake, voltage rails), while a comparable HPE Gen10 typically publishes a handful.

---

### `redfish_performance_scrape_duration_seconds`

Total time taken to scrape all performance-endpoint metrics for one target.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial` |
| **Unit** | Seconds |

---

## `/sensors` endpoint

Scrapes raw sensor readings from the chassis sensor collection.

### `redfish_sensors`

A single gauge metric covering all non-energy sensor readings. Each sensor is represented as one time series identified by its labels.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial`, `id`, `name`, `type`, `unit`, `physical_context`, `electrical_context` |
| **Source** | `GET /redfish/v1/Chassis/{id}/Sensors/{id}` |

Only sensors with `Status.State = Enabled` and a non-null `Reading` field are emitted. Energy sensors (`ReadingUnits` of `kW.h`, `kWh`, or `Joules`) are emitted as `redfish_sensors_total` instead (see below).

#### Sensor label descriptions

| Label | Redfish field | Description |
|---|---|---|
| `id` | `Id` | Unique sensor identifier |
| `name` | `Name` | Human-readable sensor name |
| `type` | `ReadingType` | Sensor reading type (e.g. `Voltage`, `Current`, `Temperature`) |
| `unit` | `ReadingUnits` | Unit of the reading (e.g. `V`, `A`, `Cel`) |
| `physical_context` | `PhysicalContext` | Physical location context (e.g. `CPU`, `Memory`, `Chassis`) |
| `electrical_context` | `ElectricalContext` | Electrical circuit context (e.g. `Line1`, `Total`) |

---

### `redfish_sensors_total`

Counter metric for cumulative energy sensor readings. Uses the same label set as `redfish_sensors`.

| | |
|---|---|
| **Type** | Counter |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial`, `id`, `name`, `type`, `unit`, `physical_context`, `electrical_context` |
| **Source** | `GET /redfish/v1/Chassis/{id}/Sensors/{id}` |

Emitted for sensors whose `ReadingUnits` is `kW.h`, `kWh`, or `Joules`.

---

### `redfish_sensors_scrape_duration_seconds`

Total time taken to scrape all sensor-endpoint metrics for one target.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial` |
| **Unit** | Seconds |

---

## `/bios` endpoint

Scrapes BIOS settings and pending change state. This endpoint is only available for servers that expose BIOS attributes via the Redfish standard.

### `redfish_bios_pending_changes`

Indicates whether BIOS changes are pending a reboot to take effect.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial` |
| **Values** | `1` — pending changes present (`@Redfish.Settings` key exists); `0` — no pending changes |
| **Source** | `GET /redfish/v1/Systems/{id}/Bios` |

---

### `redfish_bios_<attribute_name>`

One metric per BIOS attribute, where `<attribute_name>` is the Redfish attribute name converted to `snake_case` (e.g. `AcPwrRcvry` → `redfish_bios_ac_pwr_rcvry`).

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial`, `setting_name` (and `setting_value` for string attributes) |
| **Source** | `GET /redfish/v1/Systems/{id}/Bios` → `Attributes` |

#### Value encoding

| Attribute type | Metric value |
|---|---|
| Integer or float | The numeric value directly |
| Boolean `true` | `1` |
| Boolean `false` | `0` |
| String `"Enabled"` | `1` |
| String `"Disabled"` | `0` |
| Other string | `1` (value carried in `setting_value` label) |

> **Vendor notes:** Attributes whose names start with `Broadcom` are skipped on all platforms to avoid excessively long metric names (observed on Lenovo ThinkSystem SR675 V3).

---

### `redfish_bios_scrape_duration_seconds`

Total time taken to scrape all BIOS-endpoint metrics for one target.

| | |
|---|---|
| **Type** | Gauge |
| **Labels** | `host`, `server_manufacturer`, `server_model`, `server_serial` |
| **Unit** | Seconds |

---

## Metric index

| Metric name | Type | Endpoint |
|---|---|---|
| `redfish_up` | Gauge | `/health` |
| `redfish_version` | Gauge | `/health` |
| `redfish_response_duration_seconds` | Gauge | `/health` |
| `redfish_powerstate` | Gauge | `/health` |
| `redfish_health` | Gauge | `/health` |
| `redfish_memory_correctable` | Gauge | `/health` |
| `redfish_memory_uncorrectable` | Gauge | `/health` |
| `redfish_certificate_isvalid` | Gauge | `/health` |
| `redfish_certificate_valid_hostname` | Gauge | `/health` |
| `redfish_certificate_valid_days` | Gauge | `/health` |
| `redfish_certificate_selfsigned` | Gauge | `/health` |
| `redfish_health_scrape_duration_seconds` | Gauge | `/health` |
| `redfish_firmware` | Gauge | `/firmware` |
| `redfish_firmware_scrape_duration_seconds` | Gauge | `/firmware` |
| `redfish_power` | Gauge | `/performance` |
| `redfish_temperature_Celsius` | Gauge | `/performance` |
| `redfish_performance_scrape_duration_seconds` | Gauge | `/performance` |
| `redfish_sensors` | Gauge | `/sensors` |
| `redfish_sensors_total` | Counter | `/sensors` |
| `redfish_sensors_scrape_duration_seconds` | Gauge | `/sensors` |
| `redfish_bios_pending_changes` | Gauge | `/bios` |
| `redfish_bios_<attribute>` | Gauge | `/bios` |
| `redfish_bios_scrape_duration_seconds` | Gauge | `/bios` |
