import os
import json
import time
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="bhotekoshi-ph-test"
)

client.username_pw_set(os.getenv("THINGSBOARD_TOKEN_1"))
client.tls_set()

client.connect(os.getenv("THINGSBOARD_HOST"), 8883, 60)
client.loop_start()

try:
    for _ in range(30):
        if client.is_connected():
            break
        time.sleep(0.2)

    if not client.is_connected():
        raise ConnectionError("MQTT connection failed")

    ph = 7.2

    info = client.publish(
        "v1/devices/me/telemetry",
        json.dumps({"ph": ph}),
        qos=1
    )

    info.wait_for_publish(timeout=10)

    if not info.is_published():
        raise TimeoutError("No PUBACK received")

    print(f"[TEST] pH = {ph}")
    print("[MQTT] PUBACK received")

finally:
    client.disconnect()
    client.loop_stop()