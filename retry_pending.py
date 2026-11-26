
import time

from multi_node import (
    NODES,
    make_client,
    flush_node,
    pending_count
)


def main():
    clients = {}

    try:
        # Connect the four configured devices
        for name, node in NODES.items():
            clients[name] = make_client(
                name, node["token"]
            )

        # Allow MQTT connections to establish
        deadline = time.monotonic() + 20

        while time.monotonic() < deadline:
            if all(
                client.is_connected()
                for client in clients.values()
            ):
                break
            time.sleep(0.5)

        # Retry any records still waiting in SQLite
        for name, client in clients.items():
            print(f"\nChecking {name}...")

            if not client.is_connected():
                print("Not connected; records remain pending")
                continue

            while pending_count(name) > 0:
                before = pending_count(name)

                flush_node(name, client)

                after = pending_count(name)

                if after >= before:
                    print("No progress. Will retry later.")
                    break

            print(f"{name}: {pending_count(name)} pending")

    finally:
        for client in clients.values():
            client.disconnect()
            client.loop_stop()


if __name__ == "__main__":
    main()
