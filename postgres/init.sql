CREATE TABLE IF NOT EXISTS weather_stats (
    id SERIAL PRIMARY KEY,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    avg_temperature DOUBLE PRECISION,
    avg_feels_like DOUBLE PRECISION,
    avg_humidity DOUBLE PRECISION,
    avg_precipitation DOUBLE PRECISION,
    avg_wind_speed DOUBLE PRECISION,
    avg_pressure DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT weather_stats_window_unique UNIQUE (window_start, window_end)
);

CREATE INDEX IF NOT EXISTS idx_weather_stats_window_start
ON weather_stats(window_start DESC);

CREATE INDEX IF NOT EXISTS idx_weather_stats_created_at
ON weather_stats(created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_weather_history_observed_at
ON weather_history(observed_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_ecmwf_forecasts_time
ON ecmwf_forecasts(forecast_time DESC);

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

CREATE INDEX IF NOT EXISTS idx_forecast_results_target_time
ON forecast_results(target_time DESC);

CREATE TABLE IF NOT EXISTS model_metrics (
    id SERIAL PRIMARY KEY,
    model_version VARCHAR(128) NOT NULL,
    metric_name VARCHAR(64) NOT NULL,
    metric_value DOUBLE PRECISION,
    horizon_hours INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
