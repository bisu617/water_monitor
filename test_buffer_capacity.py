
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import multi_node

NODE_NAME = "Test-Node"
TEST_LIMIT = 5


def main():
    with tempfile.TemporaryDirectory(
    ignore_cleanup_errors=True
) as folder:
        database = Path(folder) / "buffer_test.db"

        with sqlite3.connect(database) as conn:
            conn.execute("""
                CREATE TABLE readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    synced INTEGER NOT NULL DEFAULT 0
                )
            """)

        def count_pending(name):
            with sqlite3.connect(database) as conn:
                return conn.execute("""
                    SELECT COUNT(*)
                    FROM readings
                    WHERE device_id = ? AND synced = 0
                """, (name,)).fetchone()[0]

        def test_save_reading(name, reading, latitude, longitude):
            with sqlite3.connect(database) as conn:
                cursor = conn.execute("""
                    INSERT INTO readings (device_id, synced)
                    VALUES (?, 0)
                """, (name,))
                return cursor.lastrowid

        def get_ids():
            with sqlite3.connect(database) as conn:
                return [
                    row[0]
                    for row in conn.execute(
                        "SELECT id FROM readings ORDER BY id"
                    )
                ]

        node = {
            "offset": 0,
            "latitude": 27.89,
            "longitude": 85.16,
        }

        print("=== SQLITE BUFFER CAPACITY TEST ===")
        print("Temporary database:", database)
        print("Test capacity:", TEST_LIMIT)
        print()

        with (
            patch.object(multi_node, "MAX_PENDING_PER_NODE", TEST_LIMIT),
            patch.object(multi_node, "pending_count", count_pending),
            patch.object(multi_node, "get_buffer_depth", count_pending),
            patch.object(multi_node, "save_reading", test_save_reading),
        ):
            for i in range(1, 7):
                print(f"\n[ATTEMPT {i}]")
                multi_node.save_node_reading(
                    NODE_NAME,
                    node,
                    elapsed_minutes=0
                )

        ids = get_ids()
        final_count = len(ids)

        print("\n===== BUFFER TEST RESULTS =====")
        print("Capacity:", TEST_LIMIT)
        print("Attempted readings:", 6)
        print("Stored readings:", final_count)
        print("Rejected readings:", 6 - final_count)
        print("Stored IDs:", ids)

        passed = (
            final_count == TEST_LIMIT
            and ids == [1, 2, 3, 4, 5]
        )

        print("Test result:", "PASS" if passed else "FAIL")
        print("===============================")

        if not passed:
            raise AssertionError(
                "Buffer capacity policy did not behave as expected"
            )


if __name__ == "__main__":
    main()
