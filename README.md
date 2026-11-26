# IoT Water Monitoring (ThingsBoard + MQTT + SQLite)

A multi-node IoT water quality monitoring simulation that:
- generates sensor telemetry for 4 virtual nodes,
- publishes to ThingsBoard over secure MQTT (TLS, QoS 1),
- buffers data locally in SQLite when offline,
- and replays pending telemetry automatically when connectivity is restored.

This project is designed for practical demos of **edge buffering + cloud sync + alarm testing** for water monitoring pipelines.

---

## 1) Features

- 4 virtual monitoring nodes with independent offsets and coordinates.
- Simulated sensors:
  - pH
  - Turbidity (NTU)
  - TDS (ppm)
  - Water temperature (°C)
  - Flow (L/min)
- Rainfall-driven contamination model with recovery curve.
- Simulated supply interruption window (flow drops to zero).
- Local durable storage with SQLite (`water_monitoring.db`).
- Per-node pending queue and replay logic.
- MQTT over TLS on port `8883`.
- QoS tests and alarm scenario injectors.
- Connectivity/outage simulation via `outage.flag`.

---

## 2) Project Structure

```text
IoT-Water-Monitoring/
├─ alarm_scenarios.py
├─ connectall.py
├─ database.py
├─ mqtt_client.py
├─ multi_node.py
├─ retry_pending.py
├─ simulator.py
├─ test_alarm.py
├─ test_dynamic_nodes.py
├─ test_flow_alarm.py
├─ test_four_nodes.py
├─ test_ph_alarm.py
├─ test_qos.py
├─ test_tds_alarm.py
├─ test_turbidity_alarm.py
└─ README.md
```

---

## 3) Requirements

- Python 3.10+ (3.11/3.12 recommended)
- ThingsBoard instance reachable from your machine
- 4 device access tokens in ThingsBoard (one per node)
- Internet/network access to MQTT TLS port `8883`

Python packages used:
- `paho-mqtt`
- `python-dotenv`

---

## 4) Setup

### 4.1 Create and activate virtual environment (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 4.2 Install dependencies

```powershell
pip install paho-mqtt python-dotenv
```

### 4.3 Create `.env`

Create a `.env` file in the project root with:

```env
THINGSBOARD_HOST=your.thingsboard.host
THINGSBOARD_TOKEN_1=token_for_node_1
THINGSBOARD_TOKEN_2=token_for_node_2
THINGSBOARD_TOKEN_3=token_for_node_3
THINGSBOARD_TOKEN_4=token_for_node_4
```

Notes:
- `THINGSBOARD_HOST` should be hostname only (no protocol prefix).
- Tokens must be unique across the four nodes.

---

## 5) Data Model (SQLite)

Database file: `water_monitoring.db`

Table: `readings`

Columns:
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `device_id` (TEXT)
- `timestamp_ms` (INTEGER)
- `ph` (REAL)
- `turbidity_ntu` (REAL)
- `tds_ppm` (REAL)
- `water_temp_c` (REAL)
- `flow_lpm` (REAL)
- `latitude` (REAL)
- `longitude` (REAL)
- `synced` (INTEGER, default `0`)

Behavior:
- Every generated reading is written to SQLite first.
- `synced=0` means pending cloud upload.
- After successful MQTT publish (PUBACK), records are marked `synced=1`.

---

## 6) Main Runtime: `multi_node.py`

Run:

```powershell
python multi_node.py
```

What it does:
1. Validates host and all 4 tokens.
2. Ensures token uniqueness.
3. Initializes SQLite database.
4. Creates one MQTT client per node.
5. Generates periodic sensor readings (every ~2 seconds by default).
6. Writes readings to SQLite.
7. Tries to flush pending records to ThingsBoard in batches.
8. Updates/Publishes `buffer_depth` telemetry.

### Simulation settings inside `multi_node.py`

- `SAMPLE_INTERVAL = 2` (seconds)
- `SIMULATION_SPEED = 60`
- `BATCH_SIZE = 5`
- `MAX_PENDING_PER_NODE = 12000`

### Node definitions

Each node has:
- token
- latitude
- longitude
- contamination time offset

Configured nodes:
- `Bidur-Node-01`
- `Timure-Node-02`
- `Betrawati-Node-03`
- `Bhotekoshi-Node-04`

### Outage simulation switch

`multi_node.py` checks for `outage.flag` in the project root:
- If file exists: publishing is paused (SQLite buffering continues).
- If file is removed: buffered data replay resumes.

Create outage:

```powershell
New-Item outage.flag -ItemType File
```

Recover:

```powershell
Remove-Item outage.flag
```

---

## 7) Supporting Scripts

### 7.1 `database.py`

Core DB helpers:
- `initialize_database()`
- `save_reading(...)`
- `get_pending_readings(limit=10)`
- `mark_as_synced(record_ids)`
- `get_buffer_depth(device_id)`

Run directly to initialize DB:

```powershell
python database.py
```

---

### 7.2 `simulator.py`

Provides simulation logic:
- `contamination_event(elapsed_minutes)`
- `supply_interruption(elapsed_minutes)`
- `generate_reading(...)`

Can run standalone:

```powershell
python simulator.py
```

---

### 7.3 `retry_pending.py`

Reconnects all configured nodes and attempts to flush remaining pending records until no progress can be made.

Run:

```powershell
python retry_pending.py
```

Use case:
- You previously had outages/disconnects and want a focused replay pass.

---

### 7.4 `connectall.py`

Quick connectivity/auth test for all four configured devices.

Run:

```powershell
python connectall.py
```

---

### 7.5 `mqtt_client.py`

Single-node MQTT publish sanity check with timestamped payload.

Run:

```powershell
python mqtt_client.py
```

---

## 8) Alarm and Scenario Testing

### 8.1 `alarm_scenarios.py`

Inject predefined scenario payloads.

Available scenarios:
- `normal`
- `turbidity_warning`
- `turbidity_critical`
- `turbidity_warning_clear`
- `turbidity_critical_clear`
- `ph_low`
- `ph_high`
- `ph_clear`
- `tds_high`
- `tds_clear`
- `flow_zero`
- `flow_clear`

Run example:

```powershell
python alarm_scenarios.py turbidity_critical
```

---

### 8.2 `test_flow_alarm.py`

Repeatedly sends `flow_zero` for a duration, then restores.

```powershell
python test_flow_alarm.py --duration 30 --interval 5
```

---

### 8.3 `test_qos.py`

Compares publish behavior/timing for QoS 0 and QoS 1.

```powershell
python test_qos.py
```

---

### 8.4 One-off alarm tests

- `test_alarm.py` – sample alarm payload test
- `test_ph_alarm.py` – pH reading test
- `test_tds_alarm.py` – TDS reading test
- `test_turbidity_alarm.py` – turbidity reading test
- `test_four_nodes.py` – sends one sample reading from each location/node
- `test_dynamic_nodes.py` – prints simulated location-wise readings

Examples:

```powershell
python test_alarm.py
python test_ph_alarm.py
python test_tds_alarm.py
python test_turbidity_alarm.py
python test_four_nodes.py
python test_dynamic_nodes.py
```

---

## 9) Typical Demo Flow

1. Configure `.env` with valid host and 4 tokens.
2. Run:

   ```powershell
   python multi_node.py
   ```

3. Observe telemetry arriving in ThingsBoard.
4. Simulate outage by creating `outage.flag`.
5. Let pending data accumulate in SQLite.
6. Remove `outage.flag` and watch replay/flush.
7. Validate alarm paths with:

   ```powershell
   python alarm_scenarios.py turbidity_critical
   python test_flow_alarm.py --duration 30 --interval 5
   ```

---

## 10) Troubleshooting

### Missing env vars
- Error: missing host/token(s)
- Fix: verify `.env` keys and values.

### TLS or connection timeout
- Check host DNS.
- Verify firewall allows outbound `8883`.
- Confirm ThingsBoard MQTT endpoint and certificates.

### Auth/connect rejected
- Verify token belongs to intended ThingsBoard device.
- Ensure each node token is unique.

### No telemetry in dashboard
- Confirm correct device is selected in ThingsBoard.
- Check script logs for publish ack / retry messages.
- Verify `outage.flag` is not present.

### Buffer keeps growing
- Likely connectivity or publish-ack issue.
- Run:

  ```powershell
  python retry_pending.py
  ```

- Check whether clients are connected and `flush_node` is succeeding.

---

## 11) Security/Operational Notes

- Do not commit `.env` with real tokens.
- Rotate access tokens if leaked.
- Current coordinates are marked as demonstration values.
- Consider adding:
  - requirements.txt / pyproject.toml
  - structured logging
  - metrics export
  - graceful service packaging (systemd / container)
  - retention/cleanup policy for SQLite

---

## 12) License

No license file is currently included in this repository. Add one if this project will be shared publicly.

---

## 13) Quick Command Reference

```powershell
# Setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install paho-mqtt python-dotenv

# Main runtime
python multi_node.py

# Replay pending
python retry_pending.py

# Device connectivity check
python connectall.py

# Alarm scenario injection
python alarm_scenarios.py turbidity_critical

# QoS test
python test_qos.py

# Flow alarm sustained test
python test_flow_alarm.py --duration 30 --interval 5
```
