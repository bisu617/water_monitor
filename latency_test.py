
import os
import csv
import time
import ssl
import uuid
import statistics
from pathlib import Path

import requests
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST", "eu.thingsboard.cloud").strip()
API_KEY = os.getenv("THINGSBOARD_API_KEY", "").strip()

MQTT_HOST = HOST if HOST.startswith("mqtt.") else f"mqtt.{HOST}"
API_HOST = HOST[5:] if HOST.startswith("mqtt.") else HOST
API_URL = f"https://{API_HOST}"

SAMPLES_PER_NODE = 50
TOPIC = "v1/devices/me/telemetry"

NODES = {
    "Bidur-Node-01": {
        "id": "9b5cec00-e7ae-11f1-a149-ef0da579dd49",
        "token": os.getenv("THINGSBOARD_TOKEN_1"),
    },
    "Timure-Node-02": {
        "id": "a3e3d820-e7ae-11f1-bf0c-b971e756f4e3",
        "token": os.getenv("THINGSBOARD_TOKEN_2"),
    },
    "Betrawati-Node-03": {
        "id": "aca3d5a0-e7ae-11f1-bf0c-b971e756f4e3",
        "token": os.getenv("THINGSBOARD_TOKEN_3"),
    },
    "Bhotekoshi-Node-04": {
        "id": "b5aaee40-e7ae-11f1-bf0c-b971e756f4e3",
        "token": os.getenv("THINGSBOARD_TOKEN_4"),
    },
}


def percentile_95(values):
    values = sorted(values)
    index = 0.95 * (len(values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    fraction = index - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def connect_node(token):
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )
    client.username_pw_set(token)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.connect(MQTT_HOST, 8883, 60)
    client.loop_start()

    deadline = time.monotonic() + 15
    while not client.is_connected():
        if time.monotonic() > deadline:
            client.loop_stop()
            raise TimeoutError("MQTT connection timed out")
        time.sleep(0.05)

    return client


def publish_samples(name, node, key):
    client = connect_node(node["token"])
    acknowledged = 0

    try:
        for i in range(SAMPLES_PER_NODE):
            # Client creation time, in Unix milliseconds.
            created_ms = int(time.time() * 1000)

            # No top-level "ts": ThingsBoard assigns server time.
            payload = f'{{"{key}": {created_ms}}}'

            info = client.publish(TOPIC, payload, qos=1)
            info.wait_for_publish(timeout=10)

            if info.is_published():
                acknowledged += 1
            else:
                print(f"[WARNING] {name} sample {i + 1} unacknowledged")

            time.sleep(0.15)

    finally:
        client.disconnect()
        client.loop_stop()

    print(
        f"[PUBLISHED] {name}: "
        f"{acknowledged}/{SAMPLES_PER_NODE} acknowledged"
    )

    return acknowledged


def fetch_stored_samples(session, device_id, key, start_ms, end_ms):
    url = (
        f"{API_URL}/api/plugins/telemetry/DEVICE/"
        f"{device_id}/values/timeseries"
    )

    response = session.get(
        url,
        params={
            "keys": key,
            "startTs": start_ms,
            "endTs": end_ms,
            "limit": 1000,
            "agg": "NONE",
            "orderBy": "ASC",
        },
        timeout=20,
    )

    response.raise_for_status()
    return response.json().get(key, [])


def summarize(label, values):
    if not values:
        print(f"{label}: no valid latency samples")
        return None

    result = {
        "node": label,
        "samples": len(values),
        "mean_ms": round(statistics.mean(values), 2),
        "median_ms": round(statistics.median(values), 2),
        "p95_ms": round(percentile_95(values), 2),
        "max_ms": round(max(values), 2),
    }

    print(
        f"{label}: N={result['samples']} | "
        f"Mean={result['mean_ms']} ms | "
        f"Median={result['median_ms']} ms | "
        f"P95={result['p95_ms']} ms | "
        f"Max={result['max_ms']} ms"
    )

    return result


def main():
    if not API_KEY:
        raise ValueError("THINGSBOARD_API_KEY is missing from .env")

    for name, node in NODES.items():
        if not node["token"]:
            raise ValueError(f"Missing MQTT token for {name}")

    run_id = uuid.uuid4().hex[:12]
    telemetry_key = f"latency_probe_{run_id}"
    start_ms = int(time.time() * 1000) - 5000

    print("=== FOUR-NODE LATENCY TEST ===")
    print("Test readings:", SAMPLES_PER_NODE * len(NODES))
    print("Run:", run_id)
    print("Telemetry key:", telemetry_key)

    ack_counts = {}

    # Publish 50 readings from each node.
    for name, node in NODES.items():
        print(f"\n[TESTING] {name}")
        ack_counts[name] = publish_samples(
            name, node, telemetry_key
        )

    end_ms = int(time.time() * 1000) + 300000

    session = requests.Session()
    session.headers.update({
        "X-Authorization": f"ApiKey {API_KEY}"
    })

    all_rows = []
    all_latencies = []
    summaries = []

    # Read back server timestamps, allowing for ingestion delay.
    for name, node in NODES.items():
        stored = []

        for attempt in range(10):
            stored = fetch_stored_samples(
                session,
                node["id"],
                telemetry_key,
                start_ms,
                end_ms,
            )

            if len(stored) >= ack_counts[name]:
                break

            time.sleep(2)

        node_latencies = []
        seen = set()

        for sample in stored:
            server_ms = int(sample["ts"])
            created_ms = int(float(sample["value"]))

            if created_ms in seen:
                continue
            seen.add(created_ms)

            latency_ms = server_ms - created_ms

            all_rows.append({
                "node": name,
                "created_ms": created_ms,
                "server_ms": server_ms,
                "latency_ms": latency_ms,
            })

            if latency_ms >= 0:
                node_latencies.append(latency_ms)
                all_latencies.append(latency_ms)

        print(
            f"[SERVER VERIFIED] {name}: "
            f"{len(stored)}/{SAMPLES_PER_NODE} stored samples"
        )

        summary = summarize(name, node_latencies)
        if summary:
            summaries.append(summary)

    print("\n===== OVERALL LATENCY STATISTICS =====")
    overall = summarize("ALL FOUR NODES", all_latencies)
    if overall:
        summaries.append(overall)

    with open(
        "latency_results.csv", "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "node", "created_ms", "server_ms", "latency_ms"
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    with open(
        "latency_summary.csv", "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "node", "samples", "mean_ms", "median_ms",
                "p95_ms", "max_ms"
            ],
        )
        writer.writeheader()
        writer.writerows(summaries)

    print("\n[FILES SAVED]")
    print("latency_results.csv")
    print("latency_summary.csv")

    total = len(all_latencies)
    if total < 200:
        print(
            f"\n[WARNING] Only {total}/200 valid samples. "
            "Check server retrieval and clock synchronization."
        )
    else:
        print("\n[SUCCESS] 200 valid latency samples collected.")


if __name__ == "__main__":
    main()
