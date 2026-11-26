import os
import json
import time
import sqlite3
from pathlib import Path
import random
from database import get_buffer_depth
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
    DATABASE_NAME
)

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST")
TOPIC = "v1/devices/me/telemetry"

# Demonstration settings
SAMPLE_INTERVAL = 2
SIMULATION_SPEED = 60
BATCH_SIZE = 5  # TEMPORARY (diagnosis): was 20
MAX_PENDING_PER_NODE = 12000

OUTAGE_FILE = Path("outage.flag")

# Approximate demonstration locations, not surveyed sensor positions.
NODES = {
    "Bidur-Node-01": {
        "token": os.getenv("THINGSBOARD_TOKEN_1"),
        "latitude": 27.89000,
        "longitude": 85.15972,
        "offset": 0
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
        "offset": 15
    }
}


def pending_count(device_name):
    with sqlite3.connect(DATABASE_NAME) as db:
        return db.execute(
            """
            SELECT COUNT(*) FROM readings
            WHERE device_id = ? AND synced = 0
            """,
            (device_name,)
        ).fetchone()[0]


def get_node_pending(device_name):
    with sqlite3.connect(DATABASE_NAME) as db:
        db.row_factory = sqlite3.Row

        rows = db.execute(
            """
            SELECT * FROM readings
            WHERE device_id = ? AND synced = 0
            ORDER BY timestamp_ms ASC, id ASC
            LIMIT ?
            """,
            (device_name, BATCH_SIZE)
        ).fetchall()

        return [dict(row) for row in rows]


def make_client(name, token):
    # Unique client ID per device (only unique within this script;
    # another program using the same ID would still conflict).
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"water-monitor-{name}",
        protocol=mqtt.MQTTv311
    )

    def on_connect(client, userdata, flags,
                   reason_code, properties):
        if reason_code.is_failure:
            print(f"[AUTH/CONNECT ERROR] {name}: {reason_code}")
        else:
            print(f"[CONNECTED] {name}")

    def on_disconnect(client, userdata, flags,
                      reason_code, properties):
        if reason_code.is_failure:
            print(f"[DISCONNECTED] {name}: {reason_code}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    client.username_pw_set(token)
    client.tls_set()
    client.tls_insecure_set(False)

    # Automatic reconnect with exponential delay
    client.reconnect_delay_set(
        min_delay=1,
        max_delay=32
    )

    client.connect_async(HOST, 8883, 60)
    client.loop_start()

    return client


def save_node_reading(name, node, elapsed_minutes):
    # Each node begins with clean water.
    # Contamination starts at a different time per location.
    node_minutes = elapsed_minutes - node["offset"]

    contamination = contamination_event(node_minutes)
    stopped = supply_interruption(node_minutes)

    reading = generate_reading(
        contamination,
        elapsed_minutes,
        stopped
    )

    # Extra telemetry fields. `name` is the same device identifier
    # used when the reading is saved in SQLite.
    reading["rssi"] = random.randint(-90, -55)
    reading["buffer_depth"] = get_buffer_depth(name)  # provisional, refreshed below

    # Capacity policy: preserve older pending records.
    # When full, reject new readings and log the loss.
    if pending_count(name) >= MAX_PENDING_PER_NODE:
        print(f"[BUFFER FULL] {name}: new reading dropped")
        return

    timestamp_ms = save_reading(
        name,
        reading,
        node["latitude"],
        node["longitude"]
    )

    # Recalculate AFTER the save so the current reading is counted
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

    # Queue depth at the moment of publishing (before rows are marked synced)
    buffer_depth = get_buffer_depth(name)

    # ThingsBoard timestamped batch telemetry
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

    try:
        info = client.publish(
            TOPIC,
            json.dumps(payload),
            qos=1
        )

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Publish error: {info.rc}")

        info.wait_for_publish(timeout=10)  # was 3

        if not info.is_published():
            raise TimeoutError("No PUBACK received")

        ids = [row["id"] for row in rows]
        updated = mark_as_synced(ids)

        remaining = pending_count(name)

        print(
            f"[FLUSHED] {name}: {updated} readings | "
            f"Remaining={remaining}"
        )

        # Send updated queue depth to ThingsBoard
        status_info = client.publish(
            TOPIC,
            json.dumps({"buffer_depth": remaining}),
            qos=1
        )

        if status_info.rc == mqtt.MQTT_ERR_SUCCESS:
            status_info.wait_for_publish(timeout=10)

            if status_info.is_published():
                print(f"[BUFFER STATUS] {name}: {remaining}")
            else:
                print(f"[STATUS RETRY NEEDED] {name}")
        else:
            print(f"[STATUS ERROR] {name}: {status_info.rc}")

    except Exception as error:
        print(f"[RETRY LATER] {name}: {error}")


def main():
    if not HOST:
        raise ValueError("Missing ThingsBoard hostname")

    for name, node in NODES.items():
        if not node["token"]:
            raise ValueError(f"Missing access token for {name}")

    tokens = [node["token"] for node in NODES.values()]
    if len(tokens) != len(set(tokens)):
        raise ValueError(
            "Two or more nodes are using the same ThingsBoard token!"
        )
    print("[CHECK] All four device tokens are unique")

    initialize_database()

    clients = {}

    print("=== FOUR-NODE WATER MONITORING SYSTEM ===")

    try:
        for name, node in NODES.items():
            clients[name] = make_client(
                name, node["token"]
            )

        start = time.monotonic()
        next_sample = start
        was_offline = False
        last_flush_attempt = {
            name: 0.0 for name in NODES
        }

        while True:
            now = time.monotonic()

            # Generate fresh readings at regular intervals
            if now >= next_sample:
                elapsed_minutes = (
                    (now - start) * SIMULATION_SPEED / 60
                )

                for name, node in NODES.items():
                    save_node_reading(
                        name, node, elapsed_minutes
                    )

                next_sample = now + SAMPLE_INTERVAL

            # Demonstration-only outage switch
            offline = OUTAGE_FILE.exists()

            if offline and not was_offline:
                print("\n[OUTAGE] MQTT publishing paused")

            if not offline and was_offline:
                print("\n[RECOVERY] Replaying SQLite buffer")

            was_offline = offline

            if not offline:
                for name, client in clients.items():
                    current_time = time.monotonic()

                    if current_time - last_flush_attempt[name] >= 3:
                        last_flush_attempt[name] = current_time
                        flush_node(name, client)

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nStopping monitoring system...")

    finally:
        for client in clients.values():
            client.disconnect()
            client.loop_stop()

        print("Monitoring stopped.")


if __name__ == "__main__":
    main()