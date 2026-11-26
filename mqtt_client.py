import os
import json
import time
import ssl
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST", "").strip()
TOKEN = os.getenv("THINGSBOARD_TOKEN_1", "").strip()

if not HOST or not TOKEN:
    raise ValueError("Missing ThingsBoard host or token in .env")

PORT = 8883  # TLS. Use 1883 and remove tls_set() for plain MQTT

reading = {
    "ph": 7.2,
    "turbidity_ntu": 5.4,
    "tds_ppm": 180,
    "water_temp_c": 20.5,
    "flow_lpm": 12.0
}

payload = {"ts": int(time.time() * 1000), "values": reading}


def on_connect(client, userdata, flags, reason_code, properties):
    print("on_connect:", reason_code)


def on_disconnect(client, userdata, flags, reason_code, properties):
    print("on_disconnect:", reason_code)


client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.username_pw_set(TOKEN)

if PORT == 8883:
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

print(f"Connecting to {HOST}:{PORT}...")

try:
    client.connect(HOST, PORT, 60)
    client.loop_start()

    start = time.monotonic()
    while not client.is_connected():
        if time.monotonic() - start > 10:
            raise TimeoutError("MQTT connection timed out (check token/port)")
        time.sleep(0.1)

    info = client.publish("v1/devices/me/telemetry", json.dumps(payload), qos=1)
    info.wait_for_publish(timeout=10)

    if not info.is_published():
        raise TimeoutError("Publish was not acknowledged")

    print("MQTT delivery acknowledged!")
    print(json.dumps(payload, indent=2))

finally:
    client.disconnect()
    client.loop_stop()