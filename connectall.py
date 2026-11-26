
import os
import ssl
import threading
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST")

DEVICES = {
    "Bidur-Node-01": os.getenv("THINGSBOARD_TOKEN_1"),
    "Bidur-Node-02": os.getenv("THINGSBOARD_TOKEN_2"),
    "Bidur-Node-03": os.getenv("THINGSBOARD_TOKEN_3"),
    "Bidur-Node-04": os.getenv("THINGSBOARD_TOKEN_4"),
}


def connect_device(device_name, token):
    if not token:
        print(f"[FAILED] {device_name}: Missing token")
        return False

    connected = threading.Event()
    result = {"success": False}

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[FAILED] {device_name}: {reason_code}")
        else:
            print(f"[CONNECTED] {device_name}")
            result["success"] = True

        connected.set()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.username_pw_set(token)

    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.tls_insecure_set(False)

    try:
        client.connect(HOST, 8883, 60)
        client.loop_start()

        if not connected.wait(timeout=10):
            print(f"[FAILED] {device_name}: Connection timeout")

        return result["success"]

    except Exception as error:
        print(f"[ERROR] {device_name}: {error}")
        return False

    finally:
        if client.is_connected():
            client.disconnect()
        client.loop_stop()


def main():
    if not HOST:
        raise ValueError("Missing THINGSBOARD_HOST in .env")

    print("=== CONNECTING FOUR IOT DEVICES ===\n")

    success_count = 0

    for device_name, token in DEVICES.items():
        if connect_device(device_name, token):
            success_count += 1

    print(f"\nConnected successfully: {success_count}/4")


if __name__ == "__main__":
    main()
