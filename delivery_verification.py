
import os
import csv
import sqlite3
import time
import requests
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("THINGSBOARD_HOST", "eu.thingsboard.cloud").strip()
API_KEY = os.getenv("THINGSBOARD_API_KEY", "").strip()

API_HOST = HOST[5:] if HOST.startswith("mqtt.") else HOST
API_URL = f"https://{API_HOST}"

DATABASE = "water_monitoring.db"

# Starting IDs recorded before the outage test.
NODES = {
    "Bidur-Node-01": {
        "id": "bf667fb0-e9a4-11f1-bf0c-b971e756f4e3",
        "start_id": 22170,
    },
    "Timure-Node-02": {
        "id": "bf634b60-e9a4-11f1-bf0c-b971e756f4e3",
        "start_id": 22171,
    },
    "Betrawati-Node-03": {
        "id": "bf5f05a0-e9a4-11f1-bf0c-b971e756f4e3",
        "start_id": 22172,
    },
    "Bhotekoshi-Node-04": {
        "id": "bf6a9e60-e9a4-11f1-bf0c-b971e756f4e3",
        "start_id": 22173,
    },
}


def load_sqlite_readings(connection, name, start_id):
    cursor = connection.execute(
        """
        SELECT id, timestamp_ms, synced
        FROM readings
        WHERE device_id = ?
          AND id > ?
        ORDER BY id
        """,
        (name, start_id)
    )

    return [
        {
            "id": int(record_id),
            "ts": int(timestamp_ms),
            "synced": int(synced),
        }
        for record_id, timestamp_ms, synced in cursor.fetchall()
    ]


def fetch_cloud_timestamps(session, device_id, readings):
    if not readings:
        return set()

    # Query slightly beyond the local timestamp range.
    start_ms = min(r["ts"] for r in readings) - 1000
    end_ms = max(r["ts"] for r in readings) + 1000

    # 60-second windows prevent oversized API responses.
    window_ms = 60000
    cloud_timestamps = set()

    url = (
        f"{API_URL}/api/plugins/telemetry/DEVICE/"
        f"{device_id}/values/timeseries"
    )

    current = start_ms

    while current <= end_ms:
        window_end = min(current + window_ms - 1, end_ms)

        response = session.get(
            url,
            params={
                "keys": "ph",
                "startTs": current,
                "endTs": window_end,
                "limit": 1000,
                "agg": "NONE",
                "orderBy": "ASC",
            },
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()
        samples = data.get("ph", [])

        if len(samples) >= 1000:
            raise RuntimeError(
                "API result reached the 1000-sample limit. "
                "Use a smaller query window."
            )

        for sample in samples:
            cloud_timestamps.add(int(sample["ts"]))

        current = window_end + 1

    return cloud_timestamps


def main():
    if not API_KEY:
        raise ValueError(
            "THINGSBOARD_API_KEY is missing from .env"
        )

    print("=== FOUR-NODE DELIVERY VERIFICATION ===")
    print("SQLite vs ThingsBoard Cloud")
    print("Mode: Read-only\n")

    connection = sqlite3.connect(DATABASE)

    session = requests.Session()
    session.headers.update({
        "X-Authorization": f"ApiKey {API_KEY}"
    })

    all_results = []
    summary_rows = []

    total_generated = 0
    total_cloud_verified = 0
    total_pending = 0
    total_missing = 0
    total_synced = 0

    try:
        for name, node in NODES.items():
            print(f"[CHECKING] {name}")

            readings = load_sqlite_readings(
                connection,
                name,
                node["start_id"]
            )

            generated = len(readings)

            # Fetch ThingsBoard telemetry timestamps.
            cloud_timestamps = fetch_cloud_timestamps(
                session,
                node["id"],
                readings
            )

            verified = 0
            synced = 0
            pending = 0
            missing = 0

            for reading in readings:
                exists_in_cloud = (
                    reading["ts"] in cloud_timestamps
                )

                if reading["synced"] == 1:
                    synced += 1
                else:
                    pending += 1

                if exists_in_cloud:
                    verified += 1
                    status = "VERIFIED"
                else:
                    missing += 1
                    status = "NOT_FOUND"

                all_results.append({
                    "node": name,
                    "sqlite_id": reading["id"],
                    "timestamp_ms": reading["ts"],
                    "sqlite_synced": reading["synced"],
                    "cloud_verified": int(exists_in_cloud),
                    "status": status,
                })

            delivery_ratio = (
                verified / generated * 100
                if generated else 0.0
            )

            summary_rows.append({
                "node": name,
                "generated": generated,
                "sqlite_synced": synced,
                "sqlite_pending": pending,
                "cloud_verified": verified,
                "not_found_in_cloud": missing,
                "delivery_ratio_percent": round(
                    delivery_ratio, 2
                ),
            })

            total_generated += generated
            total_cloud_verified += verified
            total_pending += pending
            total_missing += missing
            total_synced += synced

            print(f"  Generated:      {generated}")
            print(f"  SQLite synced:  {synced}")
            print(f"  SQLite pending: {pending}")
            print(f"  Cloud verified: {verified}")
            print(f"  Not found:      {missing}")
            print(f"  Delivery ratio: {delivery_ratio:.2f}%\n")

    finally:
        connection.close()
        session.close()

    overall_delivery = (
        total_cloud_verified / total_generated * 100
        if total_generated else 0.0
    )

    missing_percent = (
        total_missing / total_generated * 100
        if total_generated else 0.0
    )

    print("===== FINAL DELIVERY PERFORMANCE =====")
    print(f"Generated readings: {total_generated}")
    print(f"SQLite synchronized: {total_synced}")
    print(f"SQLite pending: {total_pending}")
    print(f"Cloud verified: {total_cloud_verified}")
    print(f"Not found in cloud: {total_missing}")
    print(f"Message delivery ratio: {overall_delivery:.2f}%")
    print(f"Unverified percentage: {missing_percent:.2f}%")
    print("======================================")

    with open(
        "delivery_results.csv",
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "node",
                "sqlite_id",
                "timestamp_ms",
                "sqlite_synced",
                "cloud_verified",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(all_results)

    with open(
        "delivery_summary.csv",
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "node",
                "generated",
                "sqlite_synced",
                "sqlite_pending",
                "cloud_verified",
                "not_found_in_cloud",
                "delivery_ratio_percent",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    print("\n[FILES SAVED]")
    print("delivery_results.csv")
    print("delivery_summary.csv")

    if total_pending:
        print(
            f"\n[NOTE] {total_pending} readings are still "
            "pending locally. They are not necessarily lost."
        )

    if total_missing:
        print(
            "[NOTE] Readings not found in the cloud "
            "require investigation before declaring "
            "permanent data loss."
        )


if __name__ == "__main__":
    main()
