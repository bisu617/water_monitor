
import os
import ssl
import json
import time
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

host = os.getenv("THINGSBOARD_HOST", "eu.thingsboard.cloud").strip()
mqtt_host = host if host.startswith("mqtt.") else f"mqtt.{host}"
token = os.getenv("THINGSBOARD_TOKEN_1")

if not token:
    raise ValueError("Missing THINGSBOARD_TOKEN_1 in .env")

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2
)
client.username_pw_set(token)
client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

def publish(turbidity):
    reading = {
        "ph": 7.2,
        "turbidity_ntu": turbidity,
        "tds_ppm": 180,
        "flow_lpm": 12
    }

    result = client.publish(
        "v1/devices/me/telemetry",
        json.dumps(reading),
        qos=1
    )

    result.wait_for_publish(timeout=10)

    if not result.is_published():
        raise RuntimeError("MQTT publish not confirmed")

    print(f"[SENT] Turbidity={turbidity} NTU")


try:
    client.connect(mqtt_host, 8883, 60)
    client.loop_start()

    deadline = time.monotonic() + 15

    while not client.is_connected():
        if time.monotonic() > deadline:
            raise TimeoutError("MQTT connection failed")
        time.sleep(0.1)

    print("\n=== MAP WARNING DEMONSTRATION ===")
    print("Testing Bidur-Node-01")

    # First establish normal conditions.
    publish(5)

    input(
        "\nCheck that Bidur is GREEN, "
        "then press ENTER to trigger WARNING..."
    )

    # Warning threshold > 50 NTU.
    publish(80)

    print("\nWARNING SENT!")
    print("Watch the Bidur marker turn YELLOW.")
    print("Allow a few seconds for alarm processing.")
    print("Keep the severity monitor running.")

    input(
        "\nOnce you have seen the YELLOW marker, "
        "press ENTER to restore normal water..."
    )

finally:
    if client.is_connected():
        try:
            publish(5)
            print("\n[NORMAL] Turbidity restored to 5 NTU")
            print("Bidur should return to GREEN after alarm clearing.")
        except Exception as error:
            print("[CLEAR ERROR]", error)

    client.disconnect()
    client.loop_stop()
