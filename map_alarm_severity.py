
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv(
    "THINGSBOARD_HOST",
    "eu.thingsboard.cloud"
).strip()

API_KEY = os.getenv(
    "THINGSBOARD_API_KEY",
    ""
).strip()

API_HOST = HOST[5:] if HOST.startswith("mqtt.") else HOST
API_URL = f"https://{API_HOST}"

POLL_INTERVAL = 5

NODES = {
    "Bidur-Node-01":
        "bf667fb0-e9a4-11f1-bf0c-b971e756f4e3",

    "Timure-Node-02":
        "bf634b60-e9a4-11f1-bf0c-b971e756f4e3",

    "Betrawati-Node-03":
        "bf5f05a0-e9a4-11f1-bf0c-b971e756f4e3",

    "Bhotekoshi-Node-04":
        "bf6a9e60-e9a4-11f1-bf0c-b971e756f4e3",
}

# Highest severity has the highest priority.
SEVERITY_PRIORITY = {
    "WARNING": 1,
    "MINOR": 2,
    "MAJOR": 3,
    "CRITICAL": 4,
}

VALID_SEVERITIES = set(SEVERITY_PRIORITY)


def get_active_alarms(session, device_id):
    """
    Retrieve all active alarms for a device.

    Both ACTIVE_UNACK and ACTIVE_ACK count as active.
    Cleared alarms do not count.
    """

    url = (
        f"{API_URL}/api/alarm/DEVICE/"
        f"{device_id}"
    )

    active_alarms = []
    page = 0

    while True:
        response = session.get(
            url,
            params={
                "pageSize": 100,
                "page": page,
                "sortProperty": "createdTime",
                "sortOrder": "DESC",
            },
            timeout=20,
        )

        response.raise_for_status()
        result = response.json()

        alarms = result.get("data", [])

        for alarm in alarms:
            status = str(
                alarm.get("status", "")
            ).upper()

            if status in ("ACTIVE_UNACK", "ACTIVE_ACK"):
                active_alarms.append(alarm)

        if not result.get("hasNext", False):
            break

        page += 1

    return active_alarms


def calculate_highest_severity(alarms):
    """
    Select the highest severity among active alarms.
    """

    if not alarms:
        return "NORMAL"

    severities = [
        str(alarm.get("severity", "")).upper()
        for alarm in alarms
    ]

    unknown = [
        severity
        for severity in severities
        if severity not in VALID_SEVERITIES
    ]

    if unknown:
        raise ValueError(
            f"Unknown alarm severity: {unknown}"
        )

    return max(
        severities,
        key=lambda severity:
            SEVERITY_PRIORITY[severity],
    )


def get_existing_severity(session, device_id):
    """
    Read the current stored severity attribute.
    """

    url = (
        f"{API_URL}/api/plugins/telemetry/"
        f"DEVICE/{device_id}/values/"
        f"attributes/SERVER_SCOPE"
    )

    response = session.get(
        url,
        params={
            "keys": "active_alarm_severity"
        },
        timeout=20,
    )

    response.raise_for_status()

    for item in response.json():
        if item.get("key") == "active_alarm_severity":
            return item.get("value")

    return None


def update_severity(session, device_id, severity):
    """
    Save highest active alarm severity as a
    ThingsBoard server-side device attribute.
    """

    url = (
        f"{API_URL}/api/plugins/telemetry/"
        f"DEVICE/{device_id}/SERVER_SCOPE"
    )

    response = session.post(
        url,
        json={
            "active_alarm_severity": severity
        },
        timeout=20,
    )

    response.raise_for_status()


def check_node(session, node_name, device_id):
    """
    Compare actual alarm severity with stored
    map severity and update only if necessary.
    """

    alarms = get_active_alarms(
        session,
        device_id
    )

    highest = calculate_highest_severity(
        alarms
    )

    previous = get_existing_severity(
        session,
        device_id
    )

    if previous != highest:
        update_severity(
            session,
            device_id,
            highest
        )

        print(
            f"[UPDATED] {node_name} | "
            f"{previous} -> {highest} | "
            f"Active alarms={len(alarms)}",
            flush=True,
        )
    else:
        print(
            f"[UNCHANGED] {node_name} | "
            f"Severity={highest} | "
            f"Active alarms={len(alarms)}",
            flush=True,
        )


def main():
    if not API_KEY:
        raise ValueError(
            "THINGSBOARD_API_KEY missing in .env"
        )

    session = requests.Session()

    session.headers.update({
        "X-Authorization": f"ApiKey {API_KEY}",
        "Content-Type": "application/json",
    })

    print(
        "=== FOUR-NODE MAP ALARM SEVERITY MONITOR ==="
    )
    print(f"ThingsBoard: {API_URL}")
    print(f"Polling interval: {POLL_INTERVAL}s")
    print("Source: Actual active alarms")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            for node_name, device_id in NODES.items():
                try:
                    check_node(
                        session,
                        node_name,
                        device_id
                    )

                except requests.RequestException as error:
                    print(
                        f"[API ERROR] {node_name}: {error}",
                        flush=True,
                    )

                except ValueError as error:
                    print(
                        f"[DATA ERROR] {node_name}: {error}",
                        flush=True,
                    )

            print("-" * 50, flush=True)
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n[STOPPED] Severity monitor stopped.")

    finally:
        session.close()


if __name__ == "__main__":
    main()
