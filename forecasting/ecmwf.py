from datetime import datetime, timezone

import requests
from psycopg2.extras import execute_values


ECMWF_URL = "https://api.open-meteo.com/v1/ecmwf"
ECMWF_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "surface_pressure",
]

#ham lay data tu ecm
def fetch_ecmwf_forecast(latitude, longitude, forecast_days=7):
    response = requests.get(
        ECMWF_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(ECMWF_FIELDS),
            "forecast_days": forecast_days,
            "timezone": "UTC",
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()

#ham parse JSON > list 
def build_ecmwf_rows(payload, latitude, longitude):
    run_at = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0) # lay time hien tai
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    rows = []

    for index, forecast_time in enumerate(times):
        rows.append(
            (
                run_at,
                forecast_time,
                hourly.get("temperature_2m", [None] * len(times))[index],
                hourly.get("relative_humidity_2m", [None] * len(times))[index],
                hourly.get("precipitation", [None] * len(times))[index],
                hourly.get("wind_speed_10m", [None] * len(times))[index],
                hourly.get("surface_pressure", [None] * len(times))[index],
                latitude,
                longitude,
            )
        )
    return rows

#ham chen data vao postgres
def upsert_ecmwf_rows(conn, rows):
    if not rows:
        return 0

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO ecmwf_forecasts (
                forecast_run_at,
                forecast_time,
                temperature,
                humidity,
                precipitation,
                wind_speed,
                pressure,
                latitude,
                longitude
            )
            VALUES %s
            ON CONFLICT (forecast_run_at, forecast_time) DO UPDATE SET
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


def load_latest_ecmwf(conn, latitude, longitude, forecast_days=7):
    payload = fetch_ecmwf_forecast(latitude, longitude, forecast_days=forecast_days) # call API lay du lieu forecast
    rows = build_ecmwf_rows(payload, latitude, longitude) #Payload JSON > list
    return upsert_ecmwf_rows(conn, rows) #chen vao db
