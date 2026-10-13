import json
import math
import os
from datetime import timedelta

import numpy as np
import pandas as pd

from forecasting.config import HORIZON_HOURS, SEQUENCE_HOURS, TARGET_COLUMNS

# dac trung chu ky thoi gian
TIME_FEATURES = [
    "hour_sin",
    "hour_cos",
    "day_sin",
    "day_cos",
    "month_sin",
    "month_cos",
]
FEATURE_COLUMNS = TARGET_COLUMNS + TIME_FEATURES + ["latitude", "longitude"]

#load data tu DB > DF , theo gio , dac trung thoi gian
def load_observed_weather(conn):
    history_query = """
        SELECT
            observed_at AS ts,
            temperature,
            humidity,
            precipitation,
            wind_speed,
            pressure,
            latitude,
            longitude
        FROM weather_history
    """
    realtime_query = """
        SELECT
            window_end AS ts,
            avg_temperature AS temperature,
            avg_humidity AS humidity,
            avg_precipitation AS precipitation,
            avg_wind_speed AS wind_speed,
            avg_pressure AS pressure,
            NULL::DOUBLE PRECISION AS latitude,
            NULL::DOUBLE PRECISION AS longitude
        FROM weather_stats
    """
    #truy van roi luu vao frames
    frames = []
    for query in (history_query, realtime_query):
        try:
            frame = pd.read_sql(query, conn)
            if not frame.empty:
                frames.append(frame)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(columns=["ts"] + FEATURE_COLUMNS)

    df = pd.concat(frames, ignore_index=True)  
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_localize(None)
    df = df.dropna(subset=["ts"]).sort_values("ts")
    df = df.drop_duplicates(subset=["ts"], keep="last")

    default_lat = float(os.getenv("LAT", "21.0285"))
    default_lon = float(os.getenv("LON", "105.8542"))
    df["latitude"] = df["latitude"].fillna(default_lat)
    df["longitude"] = df["longitude"].fillna(default_lon)

    df = df.set_index("ts").sort_index()
    hourly = df.resample("1h").mean(numeric_only=True) #lay data theo 1h va tinh trung binh 
    hourly[TARGET_COLUMNS] = hourly[TARGET_COLUMNS].interpolate(limit_direction="both")  #noi suy gia tri thieu
    hourly["latitude"] = hourly["latitude"].ffill().bfill().fillna(default_lat)
    hourly["longitude"] = hourly["longitude"].ffill().bfill().fillna(default_lon)
    hourly = hourly.reset_index()
    return add_time_features(hourly)

# ham tao dach trung thoi gian
def add_time_features(df):
    df = df.copy()
    ts = pd.to_datetime(df["ts"])
    hour = ts.dt.hour + ts.dt.minute / 60 # cong them phut lay gia tri thap phan
    day = ts.dt.dayofweek
    month = ts.dt.month
    #ma hoa thoi gian theo chu ki
    df["hour_sin"] = np.sin(2 * math.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * math.pi * hour / 24)
    df["day_sin"] = np.sin(2 * math.pi * day / 7)
    df["day_cos"] = np.cos(2 * math.pi * day / 7)
    df["month_sin"] = np.sin(2 * math.pi * month / 12)
    df["month_cos"] = np.cos(2 * math.pi * month / 12)
    return df

# xay dung data huan luyen va data test tu DF
def build_training_arrays(df, sequence_hours=SEQUENCE_HOURS, horizons=HORIZON_HOURS):
    max_horizon = max(horizons)  #khoang thoi gian toi thieu cho training
    needed = sequence_hours + max_horizon + 1
    if len(df) < needed:
        raise ValueError(
            f"Not enough rows for training. Need at least {needed}, got {len(df)}."
        )

    df = df.dropna(subset=FEATURE_COLUMNS + TARGET_COLUMNS).reset_index(drop=True)
    feature_values = df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    target_values = df[TARGET_COLUMNS].to_numpy(dtype=np.float32)

    x_rows = []
    y_rows = []
    for end_index in range(sequence_hours, len(df) - max_horizon):
        x_rows.append(feature_values[end_index - sequence_hours:end_index])
        future_targets = []
        for horizon in horizons:
            future_targets.extend(target_values[end_index + horizon])
        y_rows.append(future_targets)

    x = np.asarray(x_rows, dtype=np.float32)
    y = np.asarray(y_rows, dtype=np.float32)
    return x, y

# tinh toan cac tham so chuan hoa cho du lieu 
def fit_scalers(x, y):
    x_mean = x.reshape(-1, x.shape[-1]).mean(axis=0)  #gop tat ca hang thanh ma tran 2d
    x_std = x.reshape(-1, x.shape[-1]).std(axis=0)
    y_mean = y.mean(axis=0)  #tinh trung binh tung cot
    y_std = y.std(axis=0) #tinh do lech chuan tung cot
    x_std[x_std == 0] = 1   #chuyen thanh 1 de tranh chia cho 0
    y_std[y_std == 0] = 1
    return x_mean, x_std, y_mean, y_std

#chuan hoa du lieu theo tham so da tinh toan o tren
def scale_arrays(x, y, x_mean, x_std, y_mean, y_std):
    return (x - x_mean) / x_std, (y - y_mean) / y_std

# xay dung chuoi du lieu moi nhat de du doan, tra ve 2 ma tran: 1 la cac dac trung, 1 la DF goc chua duoc xu ly
def latest_sequence(df, sequence_hours=SEQUENCE_HOURS):
    if len(df) < sequence_hours:
        raise ValueError(
            f"Not enough rows for inference. Need {sequence_hours}, got {len(df)}."
        )
    seq = df.dropna(subset=FEATURE_COLUMNS).tail(sequence_hours)
    return seq[FEATURE_COLUMNS].to_numpy(dtype=np.float32), seq

#luu metada vao metadata.json ( chua thong tin cau hinh mo hinh cho interference)
def save_metadata(model_dir, metadata):
    os.makedirs(model_dir, exist_ok=True)
    with open(os.path.join(model_dir, "metadata.json"), "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2)

#doc du lieu tu file metadata.json
def load_metadata(model_dir):
    with open(os.path.join(model_dir, "metadata.json"), "r", encoding="utf-8") as file:
        return json.load(file)

#truy van ECM gan nhat 
def nearest_ecmwf(conn, target_time):
    query = """
        SELECT
            temperature,
            humidity,
            precipitation,
            wind_speed,
            pressure
        FROM ecmwf_forecasts
        WHERE forecast_run_at = (SELECT MAX(forecast_run_at) FROM ecmwf_forecasts)
        ORDER BY ABS(EXTRACT(EPOCH FROM (forecast_time - %s::timestamp))) ASC
        LIMIT 1
    """
    return pd.read_sql(query, conn, params=[target_time])

#tinh thoi diem du bao tu thoi diem hien tai va horizon
def target_time_from_latest(latest_ts, horizon_minutes):
    return latest_ts + timedelta(minutes=horizon_minutes)
