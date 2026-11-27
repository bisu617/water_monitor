# IoT Water Monitoring (ThingsBoard + MQTT + SQLite)

Four-node simulated water-quality monitoring system with:
- secure MQTT telemetry to ThingsBoard,
- local SQLite buffering during outages,
- automatic replay and delivery verification,
- alarm latency and ingestion latency benchmarking,
- map severity synchronization and dashboard JSON exports.

This repository is for simulation, integration testing, and performance measurement workflows.

---

## 1) What is included

### Core runtime
- `multi_node.py` – main four-node simulator + local buffering + replay.
- `database.py` – SQLite schema and sync helpers.
- `simulator.py` – contamination and supply interruption signal model.
- `mqtt_client.py` – single publish sanity check with MQTT ack latency output.
- `retry_pending.py` – force replay of locally pending rows.

### Alarm and quality scenario testing
- `alarm_scenarios.py` – sends predefined test telemetry states.
- `test_flow_alarm.py` – sustained zero-flow alarm test.
- `test_qos.py` – QoS 0 vs QoS 1 publish behavior.
- `warning_marker_demo.py` – interactive warning-severity map demo.
- `test_buffer_capacity.py` – local policy test for max SQLite pending buffer.

### Performance and verification
- `latency_test.py` – per-node ingestion latency benchmark (created timestamp vs server timestamp).
- `alarm_latency_test.py` – critical turbidity alarm activation latency benchmark.
- `delivery_verification.py` – SQLite vs cloud telemetry delivery audit.
- `map_alarm_severity.py` – polls active alarms and writes `active_alarm_severity` attribute for map coloring.

### Dashboards and data artifacts
- `Dashboard_Thingsboard/Overall dashboard.json` – multi-node command dashboard export.
- `Dashboard_Thingsboard/post-flood_water_quality___*.json` – station dashboard exports.
- `results/*.csv` – sample benchmark and verification outputs.

### Other
- `requirements.txt` – Python dependencies.
- `dashboards` – currently empty placeholder file.

---

## 2) Architecture summary

1. Sensor values are generated per node and saved first to SQLite.
2. Publisher flushes unsynced rows in small batches to ThingsBoard via MQTT TLS (`qos=1`).
3. On success, rows are marked `synced=1`; otherwise retained for retry.
4. If `outage.flag` exists, publishing pauses while local buffering continues.
5. On recovery, backlog is replayed and recovery throughput is printed.

---

## 3) Prerequisites

- Windows, Linux, or macOS
- Python 3.10+ (3.11/3.12 recommended)
- ThingsBoard Cloud/Server instance
- 4 ThingsBoard device tokens (one per node)
- ThingsBoard API Key (required by REST-based scripts)
- Network access to:
  - MQTT TLS port `8883`
  - HTTPS REST API of your ThingsBoard host

---

## 4) Installation

### 4.1 Clone and enter project

```powershell
git clone https://github.com/bisu617/water_monitor.git
cd water_monitor
```

### 4.2 Create virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 4.3 Install dependencies

```powershell
pip install -r requirements.txt
```

Dependencies in this repo:
- `paho-mqtt`
- `python-dotenv`
- `requests`

---

## 5) Environment configuration

Create a `.env` file in the repo root:

```env
THINGSBOARD_HOST=eu.thingsboard.cloud
THINGSBOARD_TOKEN_1=token_for_bidur
THINGSBOARD_TOKEN_2=token_for_timure
THINGSBOARD_TOKEN_3=token_for_betrawati
THINGSBOARD_TOKEN_4=token_for_bhotekoshi
THINGSBOARD_API_KEY=your_thingsboard_api_key
```

Notes:
- `THINGSBOARD_HOST` should be hostname only (no `https://`).
- Some scripts prepend `mqtt.` automatically when needed.
- `THINGSBOARD_API_KEY` is mandatory for:
  - `latency_test.py`
  - `alarm_latency_test.py`
  - `delivery_verification.py`
  - `map_alarm_severity.py`

---

## 6) Database behavior

SQLite file: `water_monitoring.db`

Table: `readings`
- `id`, `device_id`, `timestamp_ms`
- `ph`, `turbidity_ntu`, `tds_ppm`, `water_temp_c`, `flow_lpm`
- `latitude`, `longitude`
- `synced` (`0` pending, `1` uploaded)

Key points:
- Data is always stored locally first.
- Upload confirmation depends on MQTT PUBACK (`qos=1`).
- Failed publishes leave data pending for later replay.

---

## 7) Main runtime usage

Run the four-node system:

```powershell
python multi_node.py
```

Current runtime settings inside `multi_node.py`:
- `SAMPLE_INTERVAL = 2`
- `SIMULATION_SPEED = 0`
- `BATCH_SIZE = 5`
- `MAX_PENDING_PER_NODE = 12000`

Important:
- With `SIMULATION_SPEED = 0`, simulated elapsed contamination time does not progress in main loop; use scenario scripts for alarm transitions or adjust this value if you want dynamic contamination progression.

### Outage simulation

Create outage flag (publishing paused):

```powershell
New-Item outage.flag -ItemType File
```

Clear outage flag (replay resumes):

```powershell
Remove-Item outage.flag
```

When backlog clears, runtime prints recovery timing and clearance rate.

---

## 8) Script-by-script runbook

### MQTT connectivity and sanity

```powershell
python mqtt_client.py
```
- Sends one telemetry payload.
- Prints MQTT ack latency in ms.

```powershell
python retry_pending.py
```
- Reconnects nodes and flushes pending SQLite rows.

### Scenario and alarm tests

```powershell
python alarm_scenarios.py turbidity_critical
python alarm_scenarios.py flow_zero
python alarm_scenarios.py flow_clear
```

```powershell
python test_flow_alarm.py --duration 30 --interval 5
```

```powershell
python test_qos.py
```

```powershell
python warning_marker_demo.py
```
- Interactive flow for map color transition demo.

```powershell
python test_buffer_capacity.py
```
- Verifies buffer-full policy with temporary test DB.

### Performance benchmarks

```powershell
python latency_test.py
```
Outputs:
- `latency_results.csv`
- `latency_summary.csv`

```powershell
python alarm_latency_test.py
```
Outputs:
- `alarm_latency_results.csv`

### Delivery verification

```powershell
python delivery_verification.py
```
Outputs:
- `delivery_results.csv`
- `delivery_summary.csv`

### Alarm-to-map severity synchronization

```powershell
python map_alarm_severity.py
```
- Polls active alarms every 5 seconds.
- Writes `active_alarm_severity` server attribute per node.
- Intended to drive marker color logic on map dashboards.

---

## 9) Dashboard import guide (ThingsBoard)

The folder `Dashboard_Thingsboard/` contains full dashboard exports.

### Import steps
1. Open ThingsBoard.
2. Go to Dashboards.
3. Choose Import Dashboard.
4. Select one JSON file from `Dashboard_Thingsboard/`.
5. Confirm entity IDs and device bindings match your environment.

Included exports:
- `Overall dashboard.json`
- `post-flood_water_quality___bidur_station.json`
- `post-flood_water_quality___bidur_station (1).json`
- `post-flood_water_quality___timure_station.json`
- `post-flood_water_quality___betrawati_station.json`
- `post-flood_water_quality___bhotekoshi_station.json`

---

## 10) Results files

Sample artifacts are stored under `results/`:
- `latency_results.csv`
- `latency_summary.csv`
- `alarm_latency_results.csv`
- `delivery_results.csv`
- `delivery_summary.csv`

These are example outputs and can be regenerated by rerunning scripts.

---

## 11) Common issues and fixes

### Missing env values
- Symptom: script raises missing host/token/API key errors.
- Fix: verify `.env` keys and spelling.

### MQTT timeout / no PUBACK
- Check token validity and host.
- Confirm outbound port `8883`.
- Check TLS interception/firewall behavior.

### API key auth failures
- Symptom: REST scripts fail with unauthorized/forbidden.
- Fix: verify `THINGSBOARD_API_KEY` and scope.

### Backlog never drains
- Confirm `outage.flag` is removed.
- Check `multi_node.py` logs for `[RETRY LATER]` publish errors.
- Run `python retry_pending.py`.

### Dashboard shows stale severity color
- Keep `map_alarm_severity.py` running.
- Confirm `active_alarm_severity` attribute updates on the device.

---

## 12) Security notes

- Never commit `.env` with real tokens/API keys.
- Rotate tokens/API keys if leaked.
- Treat simulated metrics as synthetic test data, not compliance evidence.

---

## 13) Quick start (minimum)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# configure .env first
python multi_node.py
```

---

## 14) Repository status

This README reflects the current code and files present in this repository as of the latest update, including the new benchmark, verification, dashboard, and mapping scripts.
