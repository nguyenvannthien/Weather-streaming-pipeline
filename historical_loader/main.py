import os
import time
from datetime import date, timedelta

import psycopg2
import requests
from psycopg2.extras import execute_values


ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "surface_pressure",
]


def get_env_float(name, default):
    return float(os.getenv(name, default))


def get_env_int(name, default):
    return int(os.getenv(name, default))


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB", "weather_db"),
        user=os.getenv("POSTGRES_USER", "weather_user"),
        password=os.getenv("POSTGRES_PASSWORD", "weather_password"),
    )


def wait_for_postgres(max_attempts=30, delay_seconds=2):
    for attempt in range(1, max_attempts + 1):
        try:
            conn = get_connection()
            conn.close()
            return
        except psycopg2.OperationalError as exc:
            if attempt == max_attempts:
                raise exc
            time.sleep(delay_seconds)


def ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS weather_history (
                id SERIAL PRIMARY KEY,
                observed_at TIMESTAMP NOT NULL UNIQUE,
                temperature DOUBLE PRECISION,
                humidity DOUBLE PRECISION,
                precipitation DOUBLE PRECISION,
                wind_speed DOUBLE PRECISION,
                pressure DOUBLE PRECISION,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                source VARCHAR(64) DEFAULT 'open_meteo_archive',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weather_history_observed_at
            ON weather_history(observed_at DESC);
            """
        )
    conn.commit()


def fetch_history(latitude, longitude, start_date, end_date):
    response = requests.get(
        ARCHIVE_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(HOURLY_FIELDS),
            "timezone": "UTC",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def build_rows(payload, latitude, longitude):
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    temperatures = hourly.get("temperature_2m", [])
    humidities = hourly.get("relative_humidity_2m", [])
    precipitations = hourly.get("precipitation", [])
    wind_speeds = hourly.get("wind_speed_10m", [])
    pressures = hourly.get("surface_pressure", [])

    rows = []
    for index, observed_at in enumerate(times):
        rows.append(
            (
                observed_at,
                temperatures[index],
                humidities[index],
                precipitations[index],
                wind_speeds[index],
                pressures[index],
                latitude,
                longitude,
            )
        )
    return rows


def upsert_rows(conn, rows):
    if not rows:
        return 0

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO weather_history (
                observed_at,
                temperature,
                humidity,
                precipitation,
                wind_speed,
                pressure,
                latitude,
                longitude
            )
            VALUES %s
            ON CONFLICT (observed_at) DO UPDATE SET
                temperature = EXCLUDED.temperature,
                humidity = EXCLUDED.humidity,
                precipitation = EXCLUDED.precipitation,
                wind_speed = EXCLUDED.wind_speed,
                pressure = EXCLUDED.pressure,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude;
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def main():
    latitude = get_env_float("LAT", "21.0285")
    longitude = get_env_float("LON", "105.8542")
    historical_years = get_env_int("HISTORICAL_YEARS", "2")

    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=365 * historical_years)

    print(
        "Loading historical weather data "
        f"from {start_date.isoformat()} to {end_date.isoformat()} "
        f"for lat={latitude}, lon={longitude}"
    )

    wait_for_postgres()
    conn = get_connection()
    try:
        ensure_table(conn)
        payload = fetch_history(latitude, longitude, start_date, end_date)
        rows = build_rows(payload, latitude, longitude)
        inserted = upsert_rows(conn, rows)
    finally:
        conn.close()

    print(f"Historical loader finished. Upserted {inserted} hourly rows.")


if __name__ == "__main__":
    main()
