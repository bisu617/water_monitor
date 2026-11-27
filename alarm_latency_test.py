
import os
import csv
import time
import ssl
import statistics
from datetime import datetime, timezone

import requests
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST", "eu.thingsboard.cloud").strip()
API_KEY = os.getenv("THINGSBOARD_API_KEY", "").strip()

MQTT_HOST = HOST if HOST.startswith("mqtt.") else f"mqtt.{HOST}"
API_HOST = HOST[5:] if HOST.startswith("mqtt.") else HOST
API_URL = f"https://{API_HOST}"

TOPIC = "v1/devices/me/telemetry"
SAFE_TURBIDITY = 100
CRITICAL_TURBIDITY = 250
TIMEOUT_SECONDS = 20
POLL_INTERVAL = 0.25

NODES = {
    "Bidur-Node-01": {
        "id": "bf667fb0-e9a4-11f1-bf0c-b971e756f4e3",
        "token": os.getenv("THINGSBOARD_TOKEN_1"),
    },
    "Timure-Node-02": {
        "id": "bf634b60-e9a4-11f1-bf0c-b971e756f4e3",
        "token": os.getenv("THINGSBOARD_TOKEN_2"),
    },
    "Betrawati-Node-03": {
        "id": "bf5f05a0-e9a4-11f1-bf0c-b971e756f4e3",
        "token": os.getenv("THINGSBOARD_TOKEN_3"),
    },
    "Bhotekoshi-Node-04": {
        "id": "bf6a9e60-e9a4-11f1-bf0c-b971e756f4e3",
        "token": os.getenv("THINGSBOARD_TOKEN_4"),
    },
}


def now_ms():
    return time.time_ns() // 1_000_000


def percentile_95(values):
    values = sorted(values)
    position = 0.95 * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def connect_mqtt(token):
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )
    client.username_pw_set(token)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.connect(MQTT_HOST, 8883, 60)
    client.loop_start()

    deadline = time.monotonic() + 15
    while not client.is_connected():
        if time.monotonic() >= deadline:
            client.loop_stop()
            raise TimeoutError("MQTT connection timed out")
        time.sleep(0.05)

    return client


def send_turbidity(client, value):
    # Server-assigned telemetry timestamp.
    payload = {
        "turbidity_ntu": value
    }

    sent_ms = now_ms()
    info = client.publish(TOPIC, __import__("json").dumps(payload), qos=1)
    info.wait_for_publish(timeout=10)

    if not info.is_published():
        raise TimeoutError("MQTT PUBACK not received")

    return sent_ms


def get_alarms(session, device_id):
    response = session.get(
        f"{API_URL}/api/alarm/DEVICE/{device_id}",
        params={
            "pageSize": 100,
            "page": 0,
            "sortProperty": "createdTime",
            "sortOrder": "DESC",
        },
        timeout=15,
    )

    response.raise_for_status()
    return response.json().get("data", [])


def is_target_alarm(alarm):
    alarm_type = str(alarm.get("type", "")).lower()
    severity = str(alarm.get("severity", "")).upper()

    return "turbidity" in alarm_type and severity == "CRITICAL"


def is_active(alarm):
    return str(alarm.get("status", "")).upper().startswith("ACTIVE")


def alarm_id(alarm):
    return alarm.get("id", {}).get("id")


def wait_until_cleared(session, device_id):
    deadline = time.monotonic() + TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        alarms = get_alarms(session, device_id)

        active = [
            alarm for alarm in alarms
            if is_target_alarm(alarm) and is_active(alarm)
        ]

        if not active:
            return True

        time.sleep(POLL_INTERVAL)

    return False


def wait_for_new_alarm(session, device_id, previous_ids, sent_ms):
    deadline = time.monotonic() + TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        alarms = get_alarms(session, device_id)

        for alarm in alarms:
            if not is_target_alarm(alarm):
                continue

            current_id = alarm_id(alarm)
            created_ms = int(alarm.get("createdTime") or 0)

            if (
                current_id
                and current_id not in previous_ids
                and created_ms >= sent_ms - 1000
            ):
                return alarm

        time.sleep(POLL_INTERVAL)

    return None


def run_one_event(session, name, node, client, number):
    device_id = node["id"]

    # Reset the device to normal turbidity before triggering.
    send_turbidity(client, SAFE_TURBIDITY)

    if not wait_until_cleared(session, device_id):
        print(f"[FAILED] {name}: existing critical alarm not cleared")
        return None

    previous_ids = {
        alarm_id(alarm)
        for alarm in get_alarms(session, device_id)
    }

    # Publish abnormal telemetry.
    sent_ms = send_turbidity(client, CRITICAL_TURBIDITY)

    # Retrieve a genuinely new server-created alarm record.
    alarm = wait_for_new_alarm(
        session, device_id, previous_ids, sent_ms
    )

    if alarm is None:
        print(f"[FAILED] Event {number}: no new alarm found")
        send_turbidity(client, SAFE_TURBIDITY)
        wait_until_cleared(session, device_id)
        return None

    created_ms = int(alarm["createdTime"])
    delay_ms = created_ms - sent_ms

    print(
        f"[ALARM {number}] {name} | "
        f"Delay={delay_ms} ms | "
        f"Type={alarm['type']}"
    )

    # Clear the alarm for the next event.
    send_turbidity(client, SAFE_TURBIDITY)
    cleared = wait_until_cleared(session, device_id)

    if not cleared:
        print(f"[WARNING] {name}: alarm did not clear in time")

    return {
        "event": number,
        "node": name,
        "alarm_id": alarm_id(alarm),
        "alarm_type": alarm.get("type"),
        "sent_ms": sent_ms,
        "alarm_created_ms": created_ms,
        "activation_delay_ms": delay_ms,
        "alarm_cleared": cleared,
    }


def main():
    if not API_KEY:
        raise ValueError("Missing THINGSBOARD_API_KEY in .env")

    for name, node in NODES.items():
        if not node["token"]:
            raise ValueError(f"Missing MQTT token for {name}")

    session = requests.Session()
    session.headers.update({
        "X-Authorization": f"ApiKey {API_KEY}"
    })

    # Validate REST API before sending any test alarms.
    first_node = next(iter(NODES.values()))
    get_alarms(session, first_node["id"])

    print("=== FOUR-NODE ALARM ACTIVATION TEST ===")
    print("Target: 10 Critical Turbidity alarm events")
    print("Normal: 100 NTU | Critical: 250 NTU")

    results = []

    # 3 Bidur, 3 Timure, 2 Betrawati, 2 Bhotekoshi.
    schedule = (
        list(NODES.keys()) * 3
    )[:10]

    clients = {}

    try:
        for name, node in NODES.items():
            clients[name] = connect_mqtt(node["token"])
            print(f"[CONNECTED] {name}")

        for number, name in enumerate(schedule, start=1):
            node = NODES[name]
            print(f"\n[TESTING] Event {number}/10: {name}")

            result = run_one_event(
                session,
                name,
                node,
                clients[name],
                number,
            )

            if result:
                results.append(result)

    finally:
        for client in clients.values():
            client.disconnect()
            client.loop_stop()

        with open(
            "alarm_latency_results.csv",
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            fields = [
                "event",
                "node",
                "alarm_id",
                "alarm_type",
                "sent_ms",
                "alarm_created_ms",
                "activation_delay_ms",
                "alarm_cleared",
            ]
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(results)

    delays = [
        row["activation_delay_ms"]
        for row in results
        if row["activation_delay_ms"] >= 0
    ]

    print("\n===== ALARM ACTIVATION PERFORMANCE =====")
    print(f"Confirmed events: {len(results)}/10")
    print(f"Nonnegative delay samples: {len(delays)}")

    if delays:
        print(f"Mean delay: {statistics.mean(delays):.2f} ms")
        print(f"Median delay: {statistics.median(delays):.2f} ms")
        print(f"P95 delay: {percentile_95(delays):.2f} ms")
        print(f"Maximum delay: {max(delays):.2f} ms")

    if len(delays) < 10:
        print("[WARNING] Fewer than 10 valid delay samples.")

    print("Saved: alarm_latency_results.csv")
    print("========================================")


if __name__ == "__main__":
    main()
