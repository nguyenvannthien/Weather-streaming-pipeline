import os
import time

import psycopg2


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


def ensure_forecasting_tables(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ecmwf_forecasts (
                id SERIAL PRIMARY KEY,
                forecast_run_at TIMESTAMP NOT NULL,
                forecast_time TIMESTAMP NOT NULL,
                temperature DOUBLE PRECISION,
                humidity DOUBLE PRECISION,
                precipitation DOUBLE PRECISION,
                wind_speed DOUBLE PRECISION,
                pressure DOUBLE PRECISION,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                source VARCHAR(64) DEFAULT 'open_meteo_ecmwf',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ecmwf_forecasts_run_time_unique
                    UNIQUE (forecast_run_at, forecast_time)
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ecmwf_forecasts_time
            ON ecmwf_forecasts(forecast_time DESC);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS forecast_results (
                id SERIAL PRIMARY KEY,
                forecast_time TIMESTAMP NOT NULL,
                target_time TIMESTAMP NOT NULL,
                horizon_minutes INTEGER NOT NULL,
                predicted_temperature DOUBLE PRECISION,
                predicted_humidity DOUBLE PRECISION,
                predicted_precipitation DOUBLE PRECISION,
                predicted_wind_speed DOUBLE PRECISION,
                predicted_pressure DOUBLE PRECISION,
                lstm_temperature DOUBLE PRECISION,
                ecmwf_temperature DOUBLE PRECISION,
                model_version VARCHAR(128),
                source VARCHAR(64) DEFAULT 'hybrid_lstm_ecmwf',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT forecast_results_time_horizon_unique
                    UNIQUE (forecast_time, horizon_minutes)
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_forecast_results_target_time
            ON forecast_results(target_time DESC);
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS model_metrics (
                id SERIAL PRIMARY KEY,
                model_version VARCHAR(128) NOT NULL,
                metric_name VARCHAR(64) NOT NULL,
                metric_value DOUBLE PRECISION,
                horizon_hours INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    conn.commit()
