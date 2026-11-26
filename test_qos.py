
import os
import json
import time
import ssl
import threading

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST")
TOKEN = os.getenv("THINGSBOARD_TOKEN_1")

TOPIC = "v1/devices/me/telemetry"


def test_qos(qos_level):
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
    client.username_pw_set(TOKEN)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

    try:
        print(f"\n=== TESTING QoS {qos_level} ===")

        client.connect(HOST, 8883, 60)
        client.loop_start()

        if not connected.wait(10):
            raise TimeoutError("Connection timed out")

        if not status["success"]:
            raise RuntimeError("Connection rejected")

        payload = {
            "ts": int(time.time() * 1000),
            "values": {
                "qos_test_level": qos_level,
                "qos_test_value": 100
            }
        }

        start = time.perf_counter()

        result = client.publish(
            TOPIC,
            json.dumps(payload),
            qos=qos_level
        )

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                f"Publish failed: {result.rc}"
            )

        result.wait_for_publish(timeout=10)

        if not result.is_published():
            raise TimeoutError("Publish timed out")

        elapsed = (time.perf_counter() - start) * 1000

        print(f"QoS Level: {qos_level}")
        print(f"Publish completed: {result.is_published()}")
        print(f"Time taken: {elapsed:.2f} ms")

        if qos_level == 0:
            print("QoS 0: No broker acknowledgement")
        elif qos_level == 1:
            print("QoS 1: PUBACK received")

    except Exception as error:
        print("Error:", error)

    finally:
        if client.is_connected():
            client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    if not HOST or not TOKEN:
        raise ValueError("Missing ThingsBoard settings in .env")

    test_qos(0)
    time.sleep(1)
    test_qos(1)
