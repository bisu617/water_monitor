import os
import json
import time
import sqlite3
from pathlib import Path
import random

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from simulator import (
    contamination_event,
    supply_interruption,
    generate_reading
)

from database import (
    initialize_database,
    save_reading,
    mark_as_synced,
    get_buffer_depth,
    DATABASE_NAME
)

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST")
TOPIC = "v1/devices/me/telemetry"

# Demonstration settings
SAMPLE_INTERVAL = 2
SIMULATION_SPEED = 0
BATCH_SIZE = 5
MAX_PENDING_PER_NODE = 12000

OUTAGE_FILE = Path("outage.flag")

# Approximate demonstration locations, not surveyed sensor positions.
# Offsets model an upstream-to-downstream contamination scenario.
NODES = {
    "Bidur-Node-01": {
        "token": os.getenv("THINGSBOARD_TOKEN_1"),
        "latitude": 27.89000,
        "longitude": 85.15972,
        "offset": 15
    },
    "Timure-Node-02": {
        "token": os.getenv("THINGSBOARD_TOKEN_2"),
        "latitude": 28.25285,
        "longitude": 85.36667,
        "offset": 5
    },
    "Betrawati-Node-03": {
        "token": os.getenv("THINGSBOARD_TOKEN_3"),
        "latitude": 27.97311,
        "longitude": 85.18595,
        "offset": 10
    },
    "Bhotekoshi-Node-04": {
        "token": os.getenv("THINGSBOARD_TOKEN_4"),
        "latitude": 28.271297,
        "longitude": 85.377649,
        "offset": 0
    }
}


def pending_count(device_name):
    with sqlite3.connect(DATABASE_NAME) as db:
        return db.execute(
            """
            SELECT COUNT(*)
            FROM readings
            WHERE device_id = ? AND synced = 0
            """,
            (device_name,)
        ).fetchone()[0]


def get_node_pending(device_name):
    with sqlite3.connect(DATABASE_NAME) as db:
        db.row_factory = sqlite3.Row

        rows = db.execute(
            """
            SELECT *
            FROM readings
            WHERE device_id = ? AND synced = 0
            ORDER BY timestamp_ms ASC, id ASC
            LIMIT ?
            """,
            (device_name, BATCH_SIZE)
        ).fetchall()

        return [dict(row) for row in rows]


def make_client(name, token):
    # Unique MQTT client identifier for each virtual node
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"water-monitor-{name}",
        protocol=mqtt.MQTTv311
    )

    def on_connect(
        client, userdata, flags, reason_code, properties
    ):
        if reason_code.is_failure:
            print(
                f"[AUTH/CONNECT ERROR] {name}: {reason_code}"
            )
        else:
            print(f"[CONNECTED] {name}")

    def on_disconnect(
        client, userdata, flags, reason_code, properties
    ):
        if reason_code.is_failure:
            print(
                f"[DISCONNECTED] {name}: {reason_code}"
            )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.username_pw_set(token)
    client.tls_set()
    client.tls_insecure_set(False)

    # Exponential reconnection delay between 1 and 32 seconds
    client.reconnect_delay_set(
        min_delay=1,
        max_delay=32
    )

    client.connect_async(HOST, 8883, 60)
    client.loop_start()

    return client


def save_node_reading(name, node, elapsed_minutes):
    # Apply each node's simulated contamination delay
    node_minutes = elapsed_minutes - node["offset"]

    contamination = contamination_event(node_minutes)
    stopped = supply_interruption(node_minutes)

    reading = generate_reading(
        contamination,
        elapsed_minutes,
        stopped
    )

    reading["rssi"] = random.randint(-90, -55)
    reading["buffer_depth"] = get_buffer_depth(name)

    # Preserve existing unsynced records when buffer is full.
    # Reject new readings and log the loss.
    if pending_count(name) >= MAX_PENDING_PER_NODE:
        print(
            f"[BUFFER FULL] {name}: new reading dropped"
        )
        return

    # Save every reading locally before attempting publication
    timestamp_ms = save_reading(
        name,
        reading,
        node["latitude"],
        node["longitude"]
    )

    reading["buffer_depth"] = get_buffer_depth(name)

    print(
        f"[SAVED] {name} | "
        f"Time={timestamp_ms} | "
        f"pH={reading['ph']} | "
        f"Turbidity={reading['turbidity_ntu']} | "
        f"TDS={reading['tds_ppm']} | "
        f"Flow={reading['flow_lpm']} | "
        f"RSSI={reading['rssi']} | "
        f"Pending={reading['buffer_depth']}"
    )


def flush_node(name, client):
    if not client.is_connected():
        return

    rows = get_node_pending(name)

    if not rows:
        return

    buffer_depth = get_buffer_depth(name)

    # Construct timestamped batch telemetry
    payload = []

    for row in rows:
        payload.append({
            "ts": row["timestamp_ms"],
            "values": {
                "ph": row["ph"],
                "turbidity_ntu": row["turbidity_ntu"],
                "tds_ppm": row["tds_ppm"],
                "water_temp_c": row["water_temp_c"],
                "flow_lpm": row["flow_lpm"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "rssi": random.randint(-90, -55),
                "buffer_depth": buffer_depth
            }
        })

    # NEW: Start measuring MQTT batch publication time
    flush_start = time.perf_counter()

    try:
        info = client.publish(
            TOPIC,
            json.dumps(payload),
            qos=1
        )

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                f"Publish error: {info.rc}"
            )

        # Wait for QoS 1 PUBACK confirmation
        info.wait_for_publish(timeout=10)

        if not info.is_published():
            raise TimeoutError(
                "No PUBACK received"
            )

        # NEW: Stop timer after MQTT confirmation
        flush_seconds = (
            time.perf_counter() - flush_start
        )

        # Mark confirmed readings as synchronized
        ids = [row["id"] for row in rows]
        updated = mark_as_synced(ids)

        remaining = pending_count(name)

        # NEW: Calculate confirmed readings per second
        throughput = (
            updated / flush_seconds
            if flush_seconds > 0
            else 0.0
        )

        # NEW: Display measured performance
        print(
            f"[FLUSHED] {name}: "
            f"{updated} readings | "
            f"Remaining={remaining} | "
            f"Time={flush_seconds:.3f}s | "
            f"Throughput={throughput:.2f} readings/sec"
        )

        # Publish current buffer depth to ThingsBoard
        status_info = client.publish(
            TOPIC,
            json.dumps({
                "buffer_depth": remaining
            }),
            qos=1
        )

        if status_info.rc == mqtt.MQTT_ERR_SUCCESS:
            status_info.wait_for_publish(
                timeout=10
            )

            if status_info.is_published():
                print(
                    f"[BUFFER STATUS] {name}: {remaining}"
                )
            else:
                print(
                    f"[STATUS RETRY NEEDED] {name}"
                )
        else:
            print(
                f"[STATUS ERROR] {name}: "
                f"{status_info.rc}"
            )

    except Exception as error:
        # Keep pending records for a future retry
        print(
            f"[RETRY LATER] {name}: {error}"
        )


def main():
    if not HOST:
        raise ValueError(
            "Missing ThingsBoard hostname"
        )

    for name, node in NODES.items():
        if not node["token"]:
            raise ValueError(
                f"Missing access token for {name}"
            )

    tokens = [
        node["token"]
        for node in NODES.values()
    ]

    if len(tokens) != len(set(tokens)):
        raise ValueError(
            "Two or more nodes are using "
            "the same ThingsBoard token!"
        )

    print(
        "[CHECK] All four device tokens are unique"
    )

    initialize_database()

    clients = {}

    print(
        "=== FOUR-NODE WATER MONITORING SYSTEM ==="
    )

    try:
        for name, node in NODES.items():
            clients[name] = make_client(
                name,
                node["token"]
            )

        start = time.monotonic()
        next_sample = start
        was_offline = False
        recovery_start = None
        initial_pending = 0

        last_flush_attempt = {
            name: 0.0
            for name in NODES
        }

        while True:
            now = time.monotonic()

            # Generate sensor readings regularly
            if now >= next_sample:
                elapsed_minutes = (
                    (now - start)
                    * SIMULATION_SPEED / 60
                )

                for name, node in NODES.items():
                    save_node_reading(
                        name,
                        node,
                        elapsed_minutes
                    )

                next_sample = (
                    now + SAMPLE_INTERVAL
                )

            # Simulated network outage
            offline = OUTAGE_FILE.exists()

            if offline and not was_offline:
                print(
                    "\n[OUTAGE] MQTT publishing paused"
                )

            if not offline and was_offline:
                recovery_start = time.perf_counter()

                initial_pending = sum(
                    pending_count(name) for name in NODES
                )

                print(
                    f"\n[RECOVERY START] "
                    f"Initial pending={initial_pending}"
                )

            was_offline = offline

            # Upload pending readings while online
            if not offline:
                for name, client in clients.items():
                    current_time = (
                        time.monotonic()
                    )

                    if (
                        current_time
                        - last_flush_attempt[name]
                        >= 3
                    ):
                        last_flush_attempt[name] = (
                            current_time
                        )

                        flush_node(
                            name,
                            client
                        )

            # Measure recovery completion across all four nodes
            if recovery_start is not None:
                total_pending = sum(
                    pending_count(name) for name in NODES
                )

                if total_pending == 0:
                    recovery_seconds = (
                        time.perf_counter() - recovery_start
                    )

                    recovery_rate = (
                        initial_pending / recovery_seconds
                        if recovery_seconds > 0
                        else 0.0
                    )

                    print("\n===== RECOVERY PERFORMANCE =====")
                    print(f"Initial backlog: {initial_pending} readings")
                    print(f"Recovery time: {recovery_seconds:.3f} seconds")
                    print(f"Backlog clearance rate: {recovery_rate:.2f} readings/sec")
                    print("Final pending readings: 0")
                    print("================================\n")

                    # Stop the timer after successful recovery
                    recovery_start = None

            time.sleep(0.2)

    except KeyboardInterrupt:
        print(
            "\nStopping monitoring system..."
        )

    finally:
        for client in clients.values():
            client.disconnect()
            client.loop_stop()

        print(
            "Monitoring stopped."
        )


if __name__ == "__main__":
    main()