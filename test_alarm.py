
import os
import ssl
import json
import time

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST")
TOKEN = os.getenv("THINGSBOARD_TOKEN_1")

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2
)

client.username_pw_set(TOKEN)
client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

client.connect(HOST, 8883, 60)
client.loop_start()

try:
    payload = {
        "ts": int(time.time() * 1000),
        "values": {
            "ph": 7.1,
            "turbidity_ntu": 250,
            "tds_ppm": 180,
            "water_temp_c": 20,
            "flow_lpm": 12
        }
    }

    result = client.publish(
        "v1/devices/me/telemetry",
        json.dumps(payload),
        qos=1
    )

    result.wait_for_publish(timeout=10)

    if result.is_published():
        print("Alarm test reading acknowledged by MQTT")
    else:
        print("Publish not confirmed")

finally:
    client.disconnect()
    client.loop_stop()
