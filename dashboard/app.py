import os

import pandas as pd
import plotly.graph_objects as go
import psycopg2
import streamlit as st


st.set_page_config(
    page_title="Dự báo thời tiết",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "weather_db")
DB_USER = os.getenv("POSTGRES_USER", "weather_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "weather_password")
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "Asia/Ho_Chi_Minh")
LOCATION_NAME = os.getenv("LOCATION_NAME", "Hà Nội")
REFRESH_SECONDS = 300

HORIZON_LABELS = {
    15: "15 phút",
    60: "1 giờ",
    180: "3 giờ",
    720: "12 giờ",
    1440: "1 ngày",
    4320: "3 ngày",
    10080: "7 ngày",
}

FORECAST_METRICS = {
    "Nhiệt độ": ("predicted_temperature", "°C", "#0066cc"),
    "Độ ẩm": ("predicted_humidity", "%", "#0066cc"),
    "Lượng mưa": ("predicted_precipitation", "mm", "#0066cc"),
    "Tốc độ gió": ("predicted_wind_speed", "km/h", "#0066cc"),
    "Áp suất": ("predicted_pressure", "hPa", "#0066cc"),
}

HISTORY_METRICS = {
    "Nhiệt độ": ("temperature", "°C", "lines"),
    "Độ ẩm": ("humidity", "%", "lines"),
    "Lượng mưa": ("precipitation", "mm", "bar"),
    "Tốc độ gió": ("wind_speed", "km/h", "lines"),
    "Áp suất": ("pressure", "hPa", "lines"),
}


st.markdown(
    """
    <style>
    :root {
        --ink: #1d1d1f;
        --muted: #6e6e73;
        --canvas: #ffffff;
        --parchment: #f5f5f7;
        --blue: #0066cc;
        --hairline: #e0e0e0;
    }
    html, body, [class*="css"] {
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--ink);
    }
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none;
    }
    [data-testid="stAppViewContainer"] {
        background: var(--canvas);
    }
    [data-testid="stHeader"] {
        background: rgba(255, 255, 255, 0.82);
        backdrop-filter: saturate(180%) blur(20px);
    }
    .block-container {
        max-width: 1440px;
        padding-top: 2.5rem;
        padding-bottom: 5rem;
    }
    h1, h2, h3 {
        color: var(--ink);
        font-weight: 600 !important;
        letter-spacing: -0.025em !important;
    }
    p {
        font-size: 17px;
        line-height: 1.47;
    }
    .dashboard-kicker {
        color: var(--blue);
        font-size: 14px;
        font-weight: 600;
        letter-spacing: -0.01em;
        margin-bottom: 8px;
    }
    .dashboard-title {
        font-size: clamp(36px, 5vw, 56px);
        line-height: 1.07;
        font-weight: 600;
        letter-spacing: -0.035em;
        margin: 0;
    }
    .dashboard-subtitle {
        color: var(--muted);
        margin: 12px 0 32px;
    }
    .weather-hero {
        background: var(--parchment);
        padding: 48px;
        margin: 24px 0 32px;
    }
    .hero-grid {
        display: grid;
        grid-template-columns: 1.2fr 1fr;
        gap: 48px;
        align-items: center;
    }
    .hero-temp {
        font-size: clamp(72px, 10vw, 116px);
        font-weight: 300;
        letter-spacing: -0.06em;
        line-height: 0.95;
    }
    .hero-location {
        font-size: 28px;
        font-weight: 600;
        letter-spacing: -0.025em;
        margin-bottom: 8px;
    }
    .hero-time, .hero-model {
        color: var(--muted);
        font-size: 14px;
    }
    .hero-details {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 24px 40px;
    }
    .detail-value {
        font-size: 24px;
        font-weight: 600;
        letter-spacing: -0.02em;
    }
    .detail-label {
        color: var(--muted);
        font-size: 14px;
        margin-top: 4px;
    }
    .forecast-strip {
        display: flex;
        gap: 12px;
        overflow-x: auto;
        padding: 4px 0 20px;
        scrollbar-width: thin;
    }
    .forecast-card {
        min-width: 176px;
        flex: 1;
        background: #fff;
        border: 1px solid var(--hairline);
        border-radius: 18px;
        padding: 22px 20px;
    }
    .forecast-horizon {
        font-size: 17px;
        font-weight: 600;
    }
    .forecast-time {
        min-height: 36px;
        color: var(--muted);
        font-size: 12px;
        margin-top: 4px;
    }
    .forecast-icon {
        font-size: 30px;
        margin: 18px 0 8px;
    }
    .forecast-temp {
        font-size: 28px;
        font-weight: 600;
        letter-spacing: -0.03em;
        margin-bottom: 16px;
    }
    .forecast-stat {
        color: #333;
        font-size: 13px;
        line-height: 1.9;
        white-space: nowrap;
    }
    .section-heading {
        font-size: 34px;
        line-height: 1.15;
        font-weight: 600;
        letter-spacing: -0.03em;
        margin: 48px 0 8px;
    }
    .section-copy {
        color: var(--muted);
        margin-bottom: 24px;
    }
    .refresh-note {
        color: var(--muted);
        font-size: 12px;
        text-align: right;
        margin-top: 24px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid var(--hairline);
    }
    .stTabs [data-baseweb="tab"] {
        height: 52px;
        padding: 0 20px;
        color: var(--muted);
        font-size: 15px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        color: var(--ink) !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: var(--blue);
    }
    div[role="radiogroup"] {
        gap: 6px;
    }
    div[role="radiogroup"] label {
        background: var(--parchment);
        border-radius: 9999px;
        min-height: 44px;
        padding: 7px 14px;
    }
    div[role="radiogroup"] label:has(input:checked) {
        background: var(--blue);
        color: white;
    }
    @media (max-width: 833px) {
        .block-container { padding: 1.5rem 1rem 3rem; }
        .weather-hero { padding: 32px 24px; }
        .hero-grid { grid-template-columns: 1fr; gap: 36px; }
        .hero-details { gap: 20px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def to_local_time(series):
    return (
        pd.to_datetime(series, utc=True)
        .dt.tz_convert(LOCAL_TIMEZONE)
        .dt.tz_localize(None)
    )


@st.cache_data(ttl=REFRESH_SECONDS)
def load_realtime():
    query = """
        SELECT
            window_start AS observed_at,
            avg_temperature AS temperature,
            avg_feels_like AS feels_like,
            avg_humidity AS humidity,
            avg_precipitation AS precipitation,
            avg_wind_speed AS wind_speed,
            avg_pressure AS pressure
        FROM weather_stats
        ORDER BY window_start DESC
        LIMIT 1;
    """
    with get_connection() as conn:
        return pd.read_sql_query(query, conn)


@st.cache_data(ttl=REFRESH_SECONDS)
def load_forecasts():
    query = """
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
    with get_connection() as conn:
        try:
            return pd.read_sql_query(query, conn)
        except Exception:
            return pd.DataFrame()


@st.cache_data(ttl=REFRESH_SECONDS)
def load_combined_history():
    query = """
        WITH combined AS (
            SELECT
                observed_at,
                temperature,
                NULL::double precision AS feels_like,
                humidity,
                precipitation,
                wind_speed,
                pressure,
                1 AS source_priority
            FROM weather_history

            UNION ALL

            SELECT
                window_start AS observed_at,
                avg_temperature AS temperature,
                avg_feels_like AS feels_like,
                avg_humidity AS humidity,
                avg_precipitation AS precipitation,
                avg_wind_speed AS wind_speed,
                avg_pressure AS pressure,
                2 AS source_priority
            FROM weather_stats
        ),
        deduplicated AS (
            SELECT DISTINCT ON (observed_at)
                observed_at,
                temperature,
                feels_like,
                humidity,
                precipitation,
                wind_speed,
                pressure
            FROM combined
            ORDER BY observed_at, source_priority DESC
        )
        SELECT
            date_trunc('day', observed_at) AS observed_at,
            AVG(temperature) AS temperature,
            AVG(feels_like) AS feels_like,
            AVG(humidity) AS humidity,
            SUM(precipitation) AS precipitation,
            AVG(wind_speed) AS wind_speed,
            AVG(pressure) AS pressure
        FROM deduplicated
        GROUP BY date_trunc('day', observed_at)
        ORDER BY observed_at;
    """
    with get_connection() as conn:
        return pd.read_sql_query(query, conn)


def format_value(value, unit, decimals=0):
    if pd.isna(value):
        return "—"
    return f"{value:.{decimals}f}{unit}"


def weather_icon(row):
    precipitation = row.get("predicted_precipitation", 0) or 0
    temperature = row.get("predicted_temperature", 25) or 25
    if precipitation >= 5:
        return "🌧️"
    if precipitation > 0.2:
        return "🌦️"
    if temperature >= 32:
        return "☀️"
    return "⛅"


def prepare_forecast_data():
    realtime = load_realtime()
    forecasts = load_forecasts()

    for frame, columns in (
        (realtime, ["observed_at"]),
        (forecasts, ["forecast_time", "target_time"]),
    ):
        if not frame.empty:
            for column in columns:
                frame[f"{column}_local"] = to_local_time(frame[column])
    return realtime, forecasts


def prepare_history_data():
    history = load_combined_history()
    if not history.empty:
        history["observed_at_local"] = to_local_time(history["observed_at"])
    return history


def chart_layout(title, unit, height=420):
    return {
        "title": {
            "text": title,
            "font": {"size": 21, "color": "#1d1d1f"},
            "x": 0,
        },
        "height": height,
        "margin": {"l": 20, "r": 20, "t": 60, "b": 30},
        "paper_bgcolor": "#ffffff",
        "plot_bgcolor": "#ffffff",
        "font": {"family": "system-ui", "color": "#1d1d1f"},
        "hovermode": "x unified",
        "showlegend": False,
        "xaxis": {
            "title": None,
            "showgrid": False,
            "linecolor": "#e0e0e0",
            "tickfont": {"color": "#6e6e73"},
        },
        "yaxis": {
            "title": unit,
            "gridcolor": "#f0f0f0",
            "zeroline": False,
            "tickfont": {"color": "#6e6e73"},
        },
    }


def render_forecast_tab(realtime, forecasts):
    if realtime.empty and forecasts.empty:
        st.info("Chưa có dữ liệu thời tiết. Hãy kiểm tra consumer và forecast-service.")
        return

    current = realtime.iloc[0] if not realtime.empty else forecasts.iloc[0]
    temperature = current.get("temperature", current.get("predicted_temperature"))
    feels_like = current.get("feels_like", temperature)
    humidity = current.get("humidity", current.get("predicted_humidity"))
    precipitation = current.get(
        "precipitation", current.get("predicted_precipitation")
    )
    wind_speed = current.get("wind_speed", current.get("predicted_wind_speed"))
    pressure = current.get("pressure", current.get("predicted_pressure"))

    if not realtime.empty:
        observed_time = current["observed_at_local"]
        time_label = f"Cập nhật lúc {observed_time:%H:%M, %d/%m/%Y}"
    else:
        observed_time = forecasts.iloc[0]["forecast_time_local"]
        time_label = f"Dự báo lúc {observed_time:%H:%M, %d/%m/%Y}"

    st.markdown(
        f"""
        <section class="weather-hero">
            <div class="hero-grid">
                <div>
                    <div class="hero-location">{LOCATION_NAME}</div>
                    <div class="hero-time">{time_label}</div>
                    <div class="hero-temp">{format_value(temperature, "°")}</div>
                    <div class="hero-model">Nhiệt độ cảm nhận {format_value(feels_like, "°")}</div>
                </div>
                <div class="hero-details">
                    <div><div class="detail-value">{format_value(humidity, "%")}</div><div class="detail-label">Độ ẩm</div></div>
                    <div><div class="detail-value">{format_value(precipitation, " mm", 1)}</div><div class="detail-label">Lượng mưa</div></div>
                    <div><div class="detail-value">{format_value(wind_speed, " km/h", 1)}</div><div class="detail-label">Tốc độ gió</div></div>
                    <div><div class="detail-value">{format_value(pressure, " hPa")}</div><div class="detail-label">Áp suất</div></div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-heading">Dự báo sắp tới</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-copy">Các mốc dự báo mới nhất từ mô hình hybrid LSTM và ECMWF.</div>',
        unsafe_allow_html=True,
    )

    if forecasts.empty:
        st.info("Chưa có kết quả dự báo. Hãy khởi động forecast-service.")
        return

    cards = []
    for _, row in forecasts.iterrows():
        target = row["target_time_local"]
        horizon_minutes = row["horizon_minutes"]
        horizon_label = HORIZON_LABELS.get(
            horizon_minutes, f"{horizon_minutes} phút"
        )
        cards.append(
            "".join(
                [
                    '<article class="forecast-card">',
                    f'<div class="forecast-horizon">{horizon_label}</div>',
                    f'<div class="forecast-time">{target:%H:%M}<br>{target:%d/%m/%Y}</div>',
                    f'<div class="forecast-icon">{weather_icon(row)}</div>',
                    f'<div class="forecast-temp">{format_value(row["predicted_temperature"], "°")}</div>',
                    f'<div class="forecast-stat">Độ ẩm&nbsp; {format_value(row["predicted_humidity"], "%")}</div>',
                    f'<div class="forecast-stat">Mưa&nbsp; {format_value(row["predicted_precipitation"], " mm", 1)}</div>',
                    f'<div class="forecast-stat">Gió&nbsp; {format_value(row["predicted_wind_speed"], " km/h", 1)}</div>',
                    f'<div class="forecast-stat">Áp suất&nbsp; {format_value(row["predicted_pressure"], " hPa")}</div>',
                    "</article>",
                ]
            )
        )
    st.markdown(
        f'<div class="forecast-strip">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-heading">Biểu đồ dự báo</div>', unsafe_allow_html=True)
    metric_name = st.radio(
        "Chọn thông số dự báo",
        list(FORECAST_METRICS),
        horizontal=True,
        label_visibility="collapsed",
    )
    column, unit, color = FORECAST_METRICS[metric_name]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=forecasts["target_time_local"],
            y=forecasts[column],
            mode="lines+markers",
            line={"color": color, "width": 3},
            marker={"color": color, "size": 8},
            fill="tozeroy" if metric_name == "Lượng mưa" else None,
            fillcolor="rgba(0, 102, 204, 0.08)",
            hovertemplate=f"%{{x|%d/%m %H:%M}}<br>%{{y:.1f}} {unit}<extra></extra>",
        )
    )
    fig.update_layout(**chart_layout(f"Dự báo {metric_name.lower()}", unit, 460))
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": False, "responsive": True},
    )

    forecast_time = forecasts["forecast_time_local"].max()
    st.caption(
        f"Phiên dự báo: {forecast_time:%H:%M %d/%m/%Y} · "
        f"Mô hình: {forecasts.iloc[0]['model_version']}"
    )


def render_history_chart(data, metric_name, config):
    column, unit, chart_type = config
    fig = go.Figure()
    has_feels_like = metric_name == "Nhiệt độ" and data["feels_like"].notna().any()
    if chart_type == "bar":
        fig.add_trace(
            go.Bar(
                x=data["observed_at_local"],
                y=data[column],
                marker_color="#0066cc",
                marker_line_width=0,
                opacity=0.78,
                hovertemplate=f"%{{x|%d/%m/%Y %H:%M}}<br>%{{y:.1f}} {unit}<extra></extra>",
            )
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=data["observed_at_local"],
                y=data[column],
                mode="lines",
                name=metric_name,
                line={"color": "#0066cc", "width": 2.4, "shape": "spline"},
                hovertemplate=f"%{{x|%d/%m/%Y %H:%M}}<br>%{{y:.1f}} {unit}<extra></extra>",
            )
        )
        if has_feels_like:
            fig.add_trace(
                go.Scatter(
                    x=data["observed_at_local"],
                    y=data["feels_like"],
                    mode="lines",
                    name="Cảm nhận",
                    line={
                        "color": "#7a7a7a",
                        "width": 1.5,
                        "dash": "dot",
                        "shape": "spline",
                    },
                    hovertemplate="%{x|%d/%m/%Y %H:%M}<br>%{y:.1f} °C<extra></extra>",
                )
            )
    fig.update_layout(**chart_layout(metric_name, unit, 500))
    fig.update_layout(
        dragmode="pan",
        uirevision=f"history-{metric_name}",
        hoverdistance=40,
        spikedistance=-1,
        xaxis={
            "title": None,
            "showgrid": False,
            "linecolor": "#e0e0e0",
            "tickfont": {"color": "#6e6e73"},
            "showspikes": True,
            "spikecolor": "#a1a1a6",
            "spikethickness": 1,
            "spikedash": "dot",
            "rangeslider": {
                "visible": True,
                "thickness": 0.1,
                "bgcolor": "#f5f5f7",
                "bordercolor": "#e0e0e0",
                "borderwidth": 1,
            },
            "rangeselector": {
                "buttons": [
                    {"count": 1, "label": "1 tháng", "step": "month", "stepmode": "backward"},
                    {"count": 3, "label": "3 tháng", "step": "month", "stepmode": "backward"},
                    {"count": 6, "label": "6 tháng", "step": "month", "stepmode": "backward"},
                    {"count": 1, "label": "1 năm", "step": "year", "stepmode": "backward"},
                    {"label": "Tất cả", "step": "all"},
                ],
                "x": 0,
                "y": 1.12,
                "bgcolor": "#f5f5f7",
                "activecolor": "#0066cc",
                "bordercolor": "#e0e0e0",
                "borderwidth": 1,
                "font": {"size": 12, "color": "#1d1d1f"},
            },
        },
    )
    if has_feels_like:
        fig.update_layout(
            showlegend=True,
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "right",
                "x": 1,
            },
        )
    return fig


def render_history_tab(history):
    st.markdown(
        '<div class="section-heading">Dữ liệu thời tiết theo thời gian</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-copy">Dữ liệu lịch sử và realtime được hợp nhất trên cùng một trục thời gian.</div>',
        unsafe_allow_html=True,
    )

    if history.empty:
        st.info("Chưa có dữ liệu lịch sử hoặc realtime trong PostgreSQL.")
        return

    history = history.sort_values("observed_at_local")
    start_time = history["observed_at_local"].min()
    end_time = history["observed_at_local"].max()
    st.caption(
        f"{len(history):,} ngày dữ liệu · "
        f"{start_time:%d/%m/%Y} đến {end_time:%d/%m/%Y}"
    )

    for metric_name, config in HISTORY_METRICS.items():
        st.plotly_chart(
            render_history_chart(history, metric_name, config),
            use_container_width=True,
            config={
                "displayModeBar": True,
                "displaylogo": False,
                "responsive": True,
                "scrollZoom": True,
                "modeBarButtonsToRemove": [
                    "select2d",
                    "lasso2d",
                    "autoScale2d",
                    "toggleSpikelines",
                ],
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": f"lich-su-{metric_name.lower().replace(' ', '-')}",
                    "scale": 2,
                },
            },
            key=f"history-chart-{metric_name}",
        )



st.markdown('<h1 class="dashboard-title">Thời tiết, ngay lúc này.</h1>', unsafe_allow_html=True)



@st.experimental_fragment(run_every=REFRESH_SECONDS)
def dashboard_content():
    selected_view = st.radio(
        "Chế độ hiển thị",
        ["Dự báo", "Lịch sử thời tiết"],
        horizontal=True,
        label_visibility="collapsed",
        key="dashboard_view",
    )

    try:
        if selected_view == "Dự báo":
            realtime, forecasts = prepare_forecast_data()
        else:
            history = prepare_history_data()
    except (psycopg2.Error, pd.errors.DatabaseError) as exc:
        st.error(f"Không thể kết nối tới PostgreSQL: {exc}")
        return

    if selected_view == "Dự báo":
        render_forecast_tab(realtime, forecasts)
    else:
        render_history_tab(history)

    refreshed_at = pd.Timestamp.now(tz=LOCAL_TIMEZONE)
    st.markdown(
        f'<div class="refresh-note">Tự động cập nhật mỗi 5 phút · Lần đọc dữ liệu gần nhất {refreshed_at:%H:%M:%S}</div>',
        unsafe_allow_html=True,
    )


dashboard_content()
