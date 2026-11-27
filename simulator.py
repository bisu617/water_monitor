
import random
import time
import math
from database import initialize_database, save_reading


# Simulate rainfall-triggered contamination
def contamination_event(elapsed_minutes):
    event_start = 2
    rise_duration = 6
    washout_rate = 0.08

    if elapsed_minutes < event_start:
        return 0.0

    event_time = elapsed_minutes - event_start

    if event_time < rise_duration:
        return event_time / rise_duration

    recovery_time = event_time - rise_duration

    return math.exp(-washout_rate * recovery_time)


# Simulate a complete water supply interruption
def supply_interruption(elapsed_minutes):
    interruption_start = 10
    interruption_end = 40

    return interruption_start <= elapsed_minutes < interruption_end


# Generate readings from five virtual sensors
def generate_reading(contamination_level, elapsed_minutes, supply_stopped):

    # pH decreases non-linearly during contamination
    ph = round(
        max(5.8, 7.2 - 0.9 * contamination_level**2)
        + random.uniform(-0.05, 0.05),
        2
    )

    # Turbidity increases with contamination
    turbidity = round(
        max(
            0,
            5 + 295 * contamination_level
            + random.uniform(-2, 2)
        ),
        1
    )

    # TDS increases with contamination
    tds = round(
        180 + 370 * contamination_level
        + random.uniform(-5, 5)
    )

    # Temperature follows a 24-hour cycle
    temperature = round(
        20 + 4 * math.sin(
            2 * math.pi * (elapsed_minutes / 1440)
            - math.pi / 2
        ) + random.uniform(-0.3, 0.3),
        1
    )

    # Supply interruption makes flow exactly zero
    if supply_stopped:
        flow = 0.0
    else:
        flow = round(
            max(
                0,
                12 - 5 * contamination_level
                + random.uniform(-1, 1)
            ),
            1
        )

    return {
        "ph": ph,
        "turbidity_ntu": turbidity,
        "tds_ppm": tds,
        "water_temp_c": temperature,
        "flow_lpm": flow
    }


# Main simulation
def main():
    initialize_database()

    device_id = "Bidur-Node-01"

    # Temporary simulation coordinates
    latitude = 27.914
    longitude = 85.139

    start_time = time.time()

    # One real second represents one simulated minute
    simulation_speed = 60

    print("=== IoT WATER QUALITY MONITORING SYSTEM ===")
    print("Starting virtual ESP32-S3 sensor node...\n")

    try:
        while True:
            elapsed_seconds = time.time() - start_time

            elapsed_minutes = (
                elapsed_seconds * simulation_speed / 60
            )

            contamination_level = contamination_event(
                elapsed_minutes
            )

            supply_stopped = supply_interruption(
                elapsed_minutes
            )

            # Step 1: Generate sensor measurements
            reading = generate_reading(
                contamination_level,
                elapsed_minutes,
                supply_stopped
            )

            # Step 2: Save the reading to SQLite
            timestamp_ms = save_reading(
                device_id,
                reading,
                latitude,
                longitude
            )

            # Step 3: Display the saved readings
            print(
                f"[SQLite] Saved at {timestamp_ms} | "
                f"Minute: {elapsed_minutes:.1f} | "
                f"Contamination: {contamination_level:.2f} | "
                f"Supply stopped: {supply_stopped} | "
                f"Readings: {reading}"
            )

            time.sleep(2)

    except KeyboardInterrupt:
        print("\nSimulation stopped.")


if __name__ == "__main__":
    main()
