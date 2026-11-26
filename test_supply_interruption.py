
import os
import time
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("THINGSBOARD_TOKEN_2")
HOST = "eu.thingsboard.cloud"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(TOKEN)
client.tls_set()

client.connect(HOST, 8883, 60)
client.loop_start()

try:
    while True:
        result = client.publish(
            "v1/devices/me/telemetry",
            '{"flow_lpm": 0}',
            qos=1
        )
        result.wait_for_publish()
        print("Timure: sent flow_lpm = 0")
        time.sleep(60)
except KeyboardInterrupt:
    print("Test stopped")
finally:
    client.loop_stop()
    client.disconnect()
