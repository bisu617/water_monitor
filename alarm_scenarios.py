
import os
import json
import time
import ssl
import argparse
import threading

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST")
TOKEN = os.getenv("THINGSBOARD_TOKEN_1")

TOPIC = "v1/devices/me/telemetry"

BASELINE = {
    "ph": 7.2,
    "turbidity_ntu": 5.0,
    "tds_ppm": 180,
    "water_temp_c": 20.0,
    "flow_lpm": 12.0
}

SCENARIOS = {
    "normal": {},
    "turbidity_warning": {"turbidity_ntu": 80},
    "turbidity_critical": {"turbidity_ntu": 250},
    "turbidity_warning_clear": {"turbidity_ntu": 30},
    "turbidity_critical_clear": {"turbidity_ntu": 120},
    "ph_low": {"ph": 6.2},
    "ph_high": {"ph": 9.0},
    "ph_clear": {"ph": 7.2},
    "tds_high": {"tds_ppm": 550},
    "tds_clear": {"tds_ppm": 400},
    "flow_zero": {"flow_lpm": 0},
    "flow_clear": {"flow_lpm": 12}
}


def send_scenario(name):
    readings = BASELINE.copy()
    readings.update(SCENARIOS[name])

    connected = threading.Event()
    status = {"ok": False}

    def on_connect(client, userdata, flags,
                   reason_code, properties):
        status["ok"] = not reason_code.is_failure
        connected.set()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.username_pw_set(TOKEN)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

    try:
        client.connect(HOST, 8883, 60)
        client.loop_start()

        if not connected.wait(timeout=10):
            raise TimeoutError("Connection timed out")

        if not status["ok"]:
            raise RuntimeError("MQTT authentication failed")

        payload = {
            "ts": int(time.time() * 1000),
            "values": readings
        }

        result = client.publish(
            TOPIC,
            json.dumps(payload),
            qos=1
        )

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                f"Publish failed: {result.rc}"
            )

        result.wait_for_publish(timeout=10)

        if not result.is_published():
            raise TimeoutError("No MQTT PUBACK received")

        print(f"[SUCCESS] Scenario: {name}")
        print(f"Telemetry: {readings}")
        print("QoS 1 PUBACK received.")
        print("Check ThingsBoard alarm status.")

    finally:
        if client.is_connected():
            client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "scenario",
        choices=SCENARIOS.keys()
    )

    args = parser.parse_args()

    if not HOST or not TOKEN:
        raise ValueError("Missing ThingsBoard credentials")

    send_scenario(args.scenario)
