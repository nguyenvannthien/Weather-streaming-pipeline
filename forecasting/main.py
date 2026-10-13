import os
import time

from forecasting.config import FORECAST_INTERVAL_SECONDS
from forecasting.inference import run_once
from forecasting.train_lstm import train


def main():
    mode = os.getenv("FORECAST_MODE", "service").lower()

    if mode == "train":
        train()
        return

    if mode == "once":
        run_once()
        return

    while True:
        try:
            run_once()
        except Exception as exc:
            print(f"Forecast service error: {exc}")
        time.sleep(FORECAST_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
