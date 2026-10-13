import os
from datetime import datetime, timezone

import numpy as np
from psycopg2.extras import execute_values

from forecasting.config import (
    ECMWF_BLEND_WEIGHT,
    FORECAST_HORIZON_MINUTES,
    HORIZON_HOURS,
    MODEL_DIR,
    MODEL_VERSION,
    TARGET_COLUMNS,
)
from forecasting.db import ensure_forecasting_tables, get_connection, wait_for_postgres
from forecasting.ecmwf import load_latest_ecmwf
from forecasting.features import (
    latest_sequence,
    load_observed_weather,
    nearest_ecmwf,
    target_time_from_latest,
)

# load mo hinh tu keras và scaler tu file .npz
def load_lstm_model():
    model_path = os.path.join(MODEL_DIR, "model.keras")
    scaler_path = os.path.join(MODEL_DIR, "scaler.npz")
    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        return None, None

    from tensorflow import keras

    model = keras.models.load_model(model_path)
    scaler = np.load(scaler_path)
    return model, scaler

#
def unscale_prediction(prediction, scaler):
    return prediction * scaler["y_std"] + scaler["y_mean"]

#chuyen mang 1 chieuf du bao thanh cac moc thoi gian , dict
def prediction_to_horizon_map(prediction):
    values = {}
    index = 0
    for horizon in HORIZON_HOURS:
        values[horizon * 60] = {}
        for column in TARGET_COLUMNS:
            values[horizon * 60][column] = float(prediction[index])
            index += 1
    return values

#dam bao cac gia tri du bao trong gioi han hop le
def clamp_weather_values(values):
    values = dict(values)
    if values.get("humidity") is not None:
        values["humidity"] = max(0.0, min(100.0, values["humidity"])) #1 -100
    if values.get("precipitation") is not None:
        values["precipitation"] = max(0.0, values["precipitation"]) #k âm
    if values.get("wind_speed") is not None:
        values["wind_speed"] = max(0.0, values["wind_speed"])
    return values

# ket hop lstm va ecmwf de du bao, neu khong co du lieu ecmwf thi chi tra ve du lieu lstm
def blend_lstm_ecmwf(lstm_values, ecmwf_values):
    if not ecmwf_values:
        return clamp_weather_values(lstm_values)

    blended = {}
    for column in TARGET_COLUMNS:
        lstm_value = lstm_values.get(column)
        ecmwf_value = ecmwf_values.get(column)
        if lstm_value is None:
            blended[column] = ecmwf_value
        elif ecmwf_value is None:
            blended[column] = lstm_value
        else:
            blended[column] = (
                (1 - ECMWF_BLEND_WEIGHT) * lstm_value
                + ECMWF_BLEND_WEIGHT * ecmwf_value
            )
    return clamp_weather_values(blended)

#lay data cua ecmwf
def ecmwf_values_for_target(conn, target_time):
    ecmwf_frame = nearest_ecmwf(conn, target_time)
    if ecmwf_frame.empty:
        return {}
    return ecmwf_frame.iloc[0].to_dict()

#du bao ngan han 15p dung noi suy tuyen tinh
def nowcast_15m(df, conn, target_time):
    ecmwf_values = ecmwf_values_for_target(conn, target_time)
    if df.empty:
        return clamp_weather_values(ecmwf_values), ecmwf_values

    latest = df.tail(1).iloc[0]
    previous = df.tail(2).head(1).iloc[0] if len(df) >= 2 else latest
    trend_values = {}
    for column in TARGET_COLUMNS:
        trend_values[column] = float(latest[column] + 0.25 * (latest[column] - previous[column]))

    return blend_lstm_ecmwf(trend_values, ecmwf_values), ecmwf_values

# chen , cap nhat data vao bang du lieu chua ketqua
def upsert_forecasts(conn, rows):
    if not rows:
        return 0

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO forecast_results (
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
            )
            VALUES %s
            ON CONFLICT (forecast_time, horizon_minutes) DO UPDATE SET
                target_time = EXCLUDED.target_time,
                predicted_temperature = EXCLUDED.predicted_temperature,
                predicted_humidity = EXCLUDED.predicted_humidity,
                predicted_precipitation = EXCLUDED.predicted_precipitation,
                predicted_wind_speed = EXCLUDED.predicted_wind_speed,
                predicted_pressure = EXCLUDED.predicted_pressure,
                lstm_temperature = EXCLUDED.lstm_temperature,
                ecmwf_temperature = EXCLUDED.ecmwf_temperature,
                model_version = EXCLUDED.model_version,
                updated_at = CURRENT_TIMESTAMP;
            """,
            rows,
        )
    conn.commit()
    return len(rows)

# ham chinh chay ìnerence
def run_once():
    latitude = float(os.getenv("LAT", "21.0285"))
    longitude = float(os.getenv("LON", "105.8542"))

    wait_for_postgres()
    conn = get_connection()
    try:
        #tao bảng , cap nhat du lieu ecmwf
        ensure_forecasting_tables(conn)
        ecmwf_rows = load_latest_ecmwf(conn, latitude, longitude)
        print(f"Upserted {ecmwf_rows} ECMWF rows")

        #nap mo hinh va du lieu quan sat
        observed = load_observed_weather(conn)
        model, scaler = load_lstm_model()
        forecast_time = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

        rows = []
        target_15m = target_time_from_latest(forecast_time, 15)
        nowcast_values, nowcast_ecmwf = nowcast_15m(observed, conn, target_15m)
        rows.append(
            build_result_row(
                forecast_time,
                target_15m,
                15,
                nowcast_values,
                {},
                nowcast_ecmwf,
            )
        )
        # goi model du bao lstm 
        horizon_values = {}
        if model is not None and scaler is not None:
            try:
                sequence, _ = latest_sequence(observed)
                x_scaled = (sequence.reshape(1, *sequence.shape) - scaler["x_mean"]) / scaler["x_std"]
                prediction = model.predict(x_scaled, verbose=0)[0]
                prediction = unscale_prediction(prediction, scaler)
                horizon_values = prediction_to_horizon_map(prediction)
            except Exception as exc:
                print(f"LSTM inference skipped: {exc}")
        else:
            print("No trained LSTM model found. Falling back to ECMWF forecast.")
        #neu k co mo hinh lstm thi lay du lieu ecmwf gan nhat de du bao 
        latest_observed = observed.tail(1).iloc[0].to_dict() if not observed.empty else {}
        for horizon_minutes in FORECAST_HORIZON_MINUTES:
            if horizon_minutes == 15:
                continue

            target_time = target_time_from_latest(forecast_time, horizon_minutes)
            ecmwf_values = ecmwf_values_for_target(conn, target_time)
            if horizon_minutes in horizon_values:
                lstm_values = horizon_values[horizon_minutes]
                predicted_values = blend_lstm_ecmwf(lstm_values, ecmwf_values)
            elif ecmwf_values:
                lstm_values = {}
                predicted_values = clamp_weather_values(ecmwf_values)
            else:
                lstm_values = {}
                predicted_values = clamp_weather_values(
                    {
                        column: float(latest_observed.get(column, 0.0))
                        for column in TARGET_COLUMNS
                    }
                )
            rows.append(
                build_result_row(
                    forecast_time,
                    target_time,
                    horizon_minutes,
                    predicted_values,
                    lstm_values,
                    ecmwf_values,
                )
            )

        written = upsert_forecasts(conn, rows)
    finally:
        conn.close()

    print(f"Forecast inference finished. Upserted {written} forecast rows.")


def build_result_row(forecast_time, target_time, horizon_minutes, predicted, lstm, ecmwf):
    return (
        forecast_time,
        target_time,
        horizon_minutes,
        predicted.get("temperature"),
        predicted.get("humidity"),
        predicted.get("precipitation"),
        predicted.get("wind_speed"),
        predicted.get("pressure"),
        lstm.get("temperature"),
        ecmwf.get("temperature"),
        MODEL_VERSION,
    )


if __name__ == "__main__":
    run_once()
