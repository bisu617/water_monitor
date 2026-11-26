from alarm_scenarios import send_scenario
import argparse
import time

from alarm_scenarios import send_scenario


def test_flow_alarm(duration, interval):
    print("\n=== WATER FLOW INTERRUPTION TEST ===")

    print("Sending normal flow reading...")
    send_scenario("flow_clear")

    print("\nSimulating water supply interruption...")

    start = time.monotonic()

    while time.monotonic() - start <= duration + interval:
        elapsed = time.monotonic() - start

        print(f"\nElapsed: {elapsed:.1f} seconds")
        print("Flow: 0 L/min")

        send_scenario("flow_zero")

        time.sleep(interval)

    print("\nRestoring water supply...")
    send_scenario("flow_clear")

    print("\nTest complete.")
    print("Check ThingsBoard alarm history.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--duration",
        type=int,
        default=30
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=5
    )

    args = parser.parse_args()

    test_flow_alarm(
        args.duration,
        args.interval
    )
