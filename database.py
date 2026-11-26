
import sqlite3
import time

DATABASE_NAME = "water_monitoring.db"


# Create the SQLite database and readings table
def initialize_database():
    connection = sqlite3.connect(DATABASE_NAME)

    # Enable Write-Ahead Logging (WAL)
    connection.execute("PRAGMA journal_mode=WAL")

    connection.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp_ms INTEGER NOT NULL,
            ph REAL,
            turbidity_ntu REAL,
            tds_ppm REAL,
            water_temp_c REAL,
            flow_lpm REAL,
            latitude REAL,
            longitude REAL,
            synced INTEGER DEFAULT 0
        )
    """)

    connection.commit()
    connection.close()

    print("SQLite database initialized successfully!")


# Save each sensor reading to SQLite
def save_reading(device_id, reading, latitude, longitude):
    timestamp_ms = int(time.time() * 1000)

    connection = sqlite3.connect(DATABASE_NAME)

    connection.execute("""
        INSERT INTO readings (
            device_id,
            timestamp_ms,
            ph,
            turbidity_ntu,
            tds_ppm,
            water_temp_c,
            flow_lpm,
            latitude,
            longitude,
            synced
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (
        device_id,
        timestamp_ms,
        reading["ph"],
        reading["turbidity_ntu"],
        reading["tds_ppm"],
        reading["water_temp_c"],
        reading["flow_lpm"],
        latitude,
        longitude
    ))

    connection.commit()
    connection.close()

    return timestamp_ms

def get_pending_readings(limit=10):
    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row

    cursor = connection.execute("""
        SELECT *
        FROM readings
        WHERE synced = 0
        ORDER BY timestamp_ms ASC, id ASC
        LIMIT ?
    """, (limit,))

    readings = [dict(row) for row in cursor.fetchall()]
    connection.close()

    return readings

def mark_as_synced(record_ids):
    if not record_ids:
        return 0

    connection = sqlite3.connect(DATABASE_NAME)

    placeholders = ",".join("?" for _ in record_ids)

    cursor = connection.execute(
        f"""
        UPDATE readings
        SET synced = 1
        WHERE id IN ({placeholders})
        AND synced = 0
        """,
        record_ids
    )

    updated_count = cursor.rowcount

    connection.commit()
    connection.close()

    return updated_count

def get_buffer_depth(device_id):
    with sqlite3.connect("water_monitoring.db") as conn:
        result = conn.execute(
            """
            SELECT COUNT(*)
            FROM readings
            WHERE device_id = ? AND synced = 0
            """,
            (device_id,)
        ).fetchone()

    return result[0]

if __name__ == "__main__":
    initialize_database()
