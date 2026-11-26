
import os
import json
import ssl
import threading
import time

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST")

NODES = {
    "Kathmandu": ("THINGSBOARD_TOKEN_1", 27.7088, 85.3272),
    "Bhaktapur": ("THINGSBOARD_TOKEN_2", 27.6730, 85.4301),
    "Lalitpur": ("THINGSBOARD_TOKEN_3", 27.6766, 85.3166),
    "Kaski": ("THINGSBOARD_TOKEN_4", 28.2095, 83.9914)
}


def send_test_reading(location, token_name, lat, lon):
    token = os.getenv(token_name)

    if not token:
        print(f"[ERROR] Missing token for {location}")
        return

    connected = threading.Event()
    status = {"success": False}

    def on_connect(client, userdata, flags,
                   reason_code, properties):
        status["success"] = not reason_code.is_failure
        connected.set()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.username_pw_set(token)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

    try:
        client.connect(HOST, 8883, 60)
        client.loop_start()

        if not connected.wait(timeout=10):
            raise TimeoutError("Connection timed out")

        if not status["success"]:
            raise RuntimeError("Connection rejected")

        payload = {
            "ts": int(time.time() * 1000),
            "values": {
                "ph": 7.2,
                "turbidity_ntu": 5.0,
                "tds_ppm": 180,
                "water_temp_c": 20.0,
                "flow_lpm": 12.0,
                "latitude": lat,
                "longitude": lon
            }
        }

        info = client.publish(
            "v1/devices/me/telemetry",
            json.dumps(payload),
            qos=1
        )

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError("MQTT publish failed")

        info.wait_for_publish(timeout=10)

        if not info.is_published():
            raise TimeoutError("Publish was not acknowledged")

        print(f"[SUCCESS] {location} telemetry published!")

    except Exception as error:
        print(f"[FAILED] {location}: {error}")

    finally:
        if client.is_connected():
            client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    if not HOST:
        raise ValueError("Missing THINGSBOARD_HOST")

    for location, details in NODES.items():
        send_test_reading(location, *details)
