import os

import numpy as np

from forecasting.config import HORIZON_HOURS, MODEL_DIR, MODEL_VERSION, SEQUENCE_HOURS
from forecasting.db import ensure_forecasting_tables, get_connection, wait_for_postgres
from forecasting.features import (
    FEATURE_COLUMNS,
    TARGET_COLUMNS,
    build_training_arrays,
    fit_scalers,
    load_observed_weather,
    save_metadata,
    scale_arrays,
)


def build_model(sequence_hours, feature_count, output_count):
    from tensorflow import keras
    #build model lstm voi 1 layer lstm va 2 layer dense , output la so luong bien can du bao * so gio can du bao
    model = keras.Sequential(
        [
            keras.layers.Input(shape=(sequence_hours, feature_count)), #input dau vao
            keras.layers.LSTM(64, return_sequences=False), #layer lstm voi 64 don vi nho va tra ve 1 vector
            keras.layers.Dropout(0.2),  #dropout 20% de tranh overfitting
            keras.layers.Dense(64, activation="relu"), #layer dense voi 64 don vi va ham kich hoat relu
            keras.layers.Dense(output_count), #layer dense cuoi cung voi so don vi bang so luong bien can du bao.
        ]
    )
    model.compile(optimizer="adam", loss="mse", metrics=["mae"]) #su dung thuat toan ADAM 
    return model

#ham train 
def train():
    epochs = int(os.getenv("FORECAST_TRAIN_EPOCHS", "25"))
    batch_size = int(os.getenv("FORECAST_BATCH_SIZE", "32"))

    wait_for_postgres()
    conn = get_connection()
    try:
        ensure_forecasting_tables(conn)
        df = load_observed_weather(conn)
    finally:
        conn.close()

    x, y = build_training_arrays(df)
    #tinh tham so chuan hoa
    x_mean, x_std, y_mean, y_std = fit_scalers(x, y)
    x_scaled, y_scaled = scale_arrays(x, y, x_mean, x_std, y_mean, y_std)

    split_index = max(1, int(len(x_scaled) * 0.8))  #chia du lieu thanh 80% train va 20% validation, 
    train_x, val_x = x_scaled[:split_index], x_scaled[split_index:]
    train_y, val_y = y_scaled[:split_index], y_scaled[split_index:]
    #build model
    model = build_model(SEQUENCE_HOURS, x_scaled.shape[-1], y_scaled.shape[-1])
    callbacks = []
    if len(val_x) > 0:
        from tensorflow import keras

        callbacks.append(
            keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=5,
                restore_best_weights=True,
            )
        )
    #huan luyen mo hinh 
    model.fit(
        train_x,
        train_y,
        validation_data=(val_x, val_y) if len(val_x) > 0 else None,
        epochs=epochs,
        batch_size=batch_size,
        callbacks=callbacks,
        verbose=1,
    )

    os.makedirs(MODEL_DIR, exist_ok=True)
    model.save(os.path.join(MODEL_DIR, "model.keras"))
    np.savez(
        os.path.join(MODEL_DIR, "scaler.npz"),
        x_mean=x_mean,
        x_std=x_std,
        y_mean=y_mean,
        y_std=y_std,
    )
    save_metadata(
        MODEL_DIR,
        {
            "model_version": MODEL_VERSION,
            "sequence_hours": SEQUENCE_HOURS,
            "feature_columns": FEATURE_COLUMNS,
            "target_columns": TARGET_COLUMNS,
            "horizon_hours": HORIZON_HOURS,
            "training_rows": int(len(x_scaled)),
            "epochs": epochs,
        },
    )

    print(f"Saved trained model to {MODEL_DIR}")


if __name__ == "__main__":
    train()
