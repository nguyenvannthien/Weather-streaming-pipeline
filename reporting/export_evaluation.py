import csv
import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import psycopg2


OUTPUT_DIR = Path(os.getenv("REPORT_OUTPUT_DIR", "reporting/output"))
LAT = float(os.getenv("LAT", "21.0285"))
LON = float(os.getenv("LON", "105.8542"))
WINDY_API_KEY = os.getenv("WINDY_API_KEY")

VARIABLES = {
    "temperature": ("predicted_temperature", "avg_temperature"),
    "humidity": ("predicted_humidity", "avg_humidity"),
    "precipitation": ("predicted_precipitation", "avg_precipitation"),
    "wind_speed": ("predicted_wind_speed", "avg_wind_speed"),
    "pressure": ("predicted_pressure", "avg_pressure"),
}

HORIZON_LABELS = {
    15: "15 minutes",
    60: "1 hour",
    180: "3 hours",
    720: "12 hours",
    1440: "1 day",
    4320: "3 days",
    10080: "7 days",
}


def connect():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        database=os.getenv("POSTGRES_DB", "weather_db"),
        user=os.getenv("POSTGRES_USER", "weather_user"),
        password=os.getenv("POSTGRES_PASSWORD", "weather_password"),
    )


def fetch_rows(conn, query, params=None):
    with conn.cursor() as cur:
        cur.execute(query, params or [])
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows):
    if not rows:
        return "_No data available._"

    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(format_value(row.get(header)) for header in headers) + " |")
    return "\n".join(lines)


def format_value(value):
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def evaluation_query():
    metric_blocks = []
    for variable, (predicted_col, actual_col) in VARIABLES.items():
        metric_blocks.extend(
            [
                f"AVG(ABS({predicted_col} - {actual_col})) AS mae_{variable}",
                f"AVG(POWER({predicted_col} - {actual_col}, 2)) AS mse_{variable}",
                f"SQRT(AVG(POWER({predicted_col} - {actual_col}, 2))) AS rmse_{variable}",
                (
                    f"AVG(CASE WHEN ABS({actual_col}) > 0.000001 "
                    f"THEN ABS(({predicted_col} - {actual_col}) / {actual_col}) * 100 "
                    f"ELSE NULL END) AS mape_{variable}"
                ),
            ]
        )

    return f"""
        WITH matched AS (
            SELECT
                f.horizon_minutes,
                f.forecast_time,
                f.target_time,
                f.predicted_temperature,
                f.predicted_humidity,
                f.predicted_precipitation,
                f.predicted_wind_speed,
                f.predicted_pressure,
                w.avg_temperature,
                w.avg_humidity,
                w.avg_precipitation,
                w.avg_wind_speed,
                w.avg_pressure
            FROM forecast_results f
            JOIN LATERAL (
                SELECT *
                FROM weather_stats w
                WHERE w.window_end <= f.target_time
                ORDER BY ABS(EXTRACT(EPOCH FROM (w.window_end - f.target_time))) ASC
                LIMIT 1
            ) w ON TRUE
            WHERE f.target_time <= NOW()
        )
        SELECT
            horizon_minutes,
            COUNT(*) AS sample_count,
            {", ".join(metric_blocks)}
        FROM matched
        GROUP BY horizon_minutes
        ORDER BY horizon_minutes;
    """


def forecast_query():
    return """
        SELECT
            forecast_time,
            target_time,
            horizon_minutes,
            predicted_temperature,
            predicted_humidity,
            predicted_precipitation,
            predicted_wind_speed,
            predicted_pressure,
            lstm_temperature,
            ecmwf_temperature,
            model_version
        FROM forecast_results
        WHERE forecast_time = (SELECT MAX(forecast_time) FROM forecast_results)
        ORDER BY horizon_minutes;
    """


def observed_comparison_query():
    return """
        SELECT
            f.forecast_time,
            f.target_time,
            f.horizon_minutes,
            f.predicted_temperature,
            w.avg_temperature AS actual_temperature,
            f.predicted_humidity,
            w.avg_humidity AS actual_humidity,
            f.predicted_precipitation,
            w.avg_precipitation AS actual_precipitation,
            f.predicted_wind_speed,
            w.avg_wind_speed AS actual_wind_speed,
            f.predicted_pressure,
            w.avg_pressure AS actual_pressure
        FROM forecast_results f
        JOIN LATERAL (
            SELECT *
            FROM weather_stats w
            WHERE w.window_end <= f.target_time
            ORDER BY ABS(EXTRACT(EPOCH FROM (w.window_end - f.target_time))) ASC
            LIMIT 1
        ) w ON TRUE
        WHERE f.target_time <= NOW()
        ORDER BY f.forecast_time DESC, f.horizon_minutes ASC
        LIMIT 50;
    """


def request_windy_forecast():
    if not WINDY_API_KEY:
        return []

    payload = {
        "lat": LAT,
        "lon": LON,
        "model": "ecmwf",
        "parameters": ["temp", "rh", "precip", "wind", "pressure"],
        "levels": ["surface"],
        "key": WINDY_API_KEY,
    }
    request = urllib.request.Request(
        "https://api.windy.com/api/point-forecast/v2",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"Windy request failed: HTTP {exc.code} {exc.reason}")
        return []
    except Exception as exc:
        print(f"Windy request failed: {exc}")
        return []

    return normalize_windy_rows(data)


def normalize_windy_rows(data):
    ts_values = data.get("ts", [])
    rows = []
    for index, timestamp_ms in enumerate(ts_values):
        row = {
            "forecast_time": datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).replace(tzinfo=None),
            "windy_temperature": value_at(data, "temp-surface", index),
            "windy_humidity": value_at(data, "rh-surface", index),
            "windy_precipitation": value_at(data, "precip-surface", index),
            "windy_pressure": value_at(data, "pressure-surface", index),
        }
        wind_u = value_at(data, "wind_u-surface", index)
        wind_v = value_at(data, "wind_v-surface", index)
        if wind_u is not None and wind_v is not None:
            row["windy_wind_speed"] = math.sqrt(wind_u**2 + wind_v**2) * 3.6
        else:
            row["windy_wind_speed"] = None
        rows.append(row)
    return rows


def value_at(data, key, index):
    values = data.get(key)
    if not values or index >= len(values):
        return None
    return values[index]


def build_report(metrics, latest_forecast, observed_comparison, windy_rows):
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [
        f"# Forecast Evaluation Report\n",
        f"Generated at: {generated_at}\n",
        "## MAE / MSE / RMSE / MAPE by Horizon\n",
        markdown_table(metrics),
        "\n## Latest Model Forecast\n",
        markdown_table(latest_forecast),
        "\n## Forecast vs Actual Observations\n",
        markdown_table(observed_comparison),
    ]

    if windy_rows:
        parts.extend(["\n## Windy ECMWF Forecast Data\n", markdown_table(windy_rows[:30])])
    else:
        parts.extend(
            [
                "\n## Windy ECMWF Forecast Data\n",
                (
                    "Windy data was not exported. Set `WINDY_API_KEY` to use the "
                    "Windy Point Forecast API."
                ),
            ]
        )
    return "\n".join(parts)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        metrics = fetch_rows(conn, evaluation_query())
        latest_forecast = fetch_rows(conn, forecast_query())
        observed_comparison = fetch_rows(conn, observed_comparison_query())
    finally:
        conn.close()

    windy_rows = request_windy_forecast()

    write_csv(OUTPUT_DIR / "model_metrics_by_horizon.csv", metrics)
    write_csv(OUTPUT_DIR / "latest_model_forecast.csv", latest_forecast)
    write_csv(OUTPUT_DIR / "forecast_vs_actual.csv", observed_comparison)
    write_csv(OUTPUT_DIR / "windy_forecast.csv", windy_rows)

    report = build_report(metrics, latest_forecast, observed_comparison, windy_rows)
    (OUTPUT_DIR / "forecast_evaluation_report.md").write_text(report, encoding="utf-8")

    print(report)
    print(f"\nFiles exported to: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
