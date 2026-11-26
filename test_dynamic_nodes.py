
from simulator import (
    contamination_event,
    supply_interruption,
    generate_reading
)

LOCATIONS = {
    "Kathmandu": 0,
    "Bhaktapur": 5,
    "Lalitpur": 10,
    "Kaski": 15
}

for location, time_offset in LOCATIONS.items():
    elapsed_minutes = 8 + time_offset

    contamination = contamination_event(
        elapsed_minutes
    )

    stopped = supply_interruption(
        elapsed_minutes
    )

    reading = generate_reading(
        contamination,
        elapsed_minutes,
        stopped
    )

    print(f"\nLocation: {location}")
    print(f"Contamination: {contamination:.2f}")
    print(f"Readings: {reading}")
