# Forecast Evaluation Export

This folder contains a read-only reporting helper for the thesis evaluation section.

Run after PostgreSQL has forecast and realtime data:

```powershell
$env:POSTGRES_HOST="localhost"
$env:POSTGRES_PORT="5432"
$env:POSTGRES_DB="weather_db"
$env:POSTGRES_USER="weather_user"
$env:POSTGRES_PASSWORD="weather_password"
uv run --group dashboard python reporting/export_evaluation.py
```

Optional Windy comparison:

```powershell
$env:WINDY_API_KEY="your_windy_point_forecast_api_key"
uv run --group dashboard python reporting/export_evaluation.py
```

Outputs:

- `reporting/output/model_metrics_by_horizon.csv`
- `reporting/output/latest_model_forecast.csv`
- `reporting/output/forecast_vs_actual.csv`
- `reporting/output/windy_forecast.csv`
- `reporting/output/forecast_evaluation_report.md`
