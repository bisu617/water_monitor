
import os
import time
import json
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST")
TOKEN = os.getenv("THINGSBOARD_TOKEN_2")

if not HOST or not TOKEN:
    raise ValueError("Missing ThingsBoard hostname or Bidur access token")

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="timure-alarm-test"
)

client.username_pw_set(TOKEN)
client.tls_set()
client.connect(HOST, 8883, 60)
client.loop_start()

try:
    for _ in range(30):
        if client.is_connected():
            break
        time.sleep(0.2)

    if not client.is_connected():
        raise ConnectionError("MQTT connection failed")

    payload = {"turbidity_ntu": 5}

    info = client.publish(
        "v1/devices/me/telemetry",
        json.dumps(payload),
        qos=1
    )
    info.wait_for_publish(timeout=10)

    if not info.is_published():
        raise TimeoutError("No PUBACK received")

    print("[TEST] Turbidity = 75 NTU")
    print("[MQTT] PUBACK received")

finally:
    client.disconnect()
    client.loop_stop()
