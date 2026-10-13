import os


TARGET_COLUMNS = [
    "temperature",
    "humidity",
    "precipitation",
    "wind_speed",
    "pressure",
]

HORIZON_HOURS = [1, 3, 12, 24, 72, 168]
FORECAST_HORIZON_MINUTES = [15, 60, 180, 720, 1440, 4320, 10080]
SEQUENCE_HOURS = int(os.getenv("FORECAST_SEQUENCE_HOURS", "24"))
MODEL_VERSION = os.getenv("MODEL_VERSION", "hybrid_lstm_ecmwf_v1")
MODEL_DIR = os.getenv("MODEL_DIR", "/app/models")
ECMWF_BLEND_WEIGHT = float(os.getenv("ECMWF_BLEND_WEIGHT", "0.4"))
FORECAST_INTERVAL_SECONDS = int(os.getenv("FORECAST_INTERVAL_SECONDS", "120"))


def get_env_float(name, default):
    return float(os.getenv(name, default))


def get_env_int(name, default):
    return int(os.getenv(name, default))
