import os
import time
import json
import requests
from kafka import KafkaProducer
from dotenv import load_dotenv
from loguru import logger

# 1. doc cau hinh tu env 
load_dotenv()

KAFKA_SERVER = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = os.getenv("WEATHER_TOPIC", "weather_data")
LAT = os.getenv("LAT", "21.0285")
LON = os.getenv("LON", "105.8542")
INTERVAL = int(os.getenv("FETCH_INTERVAL_SECONDS", 60))

# 2. khoi tao kafka 
producer = KafkaProducer(
    bootstrap_servers=[KAFKA_SERVER],
    value_serializer=lambda x: json.dumps(x).encode("utf-8")
)


def fetch_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}"
        f"&longitude={LON}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "precipitation,wind_speed_10m,surface_pressure"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        current = data.get("current", {})

        weather = {
            "time": current.get("time"),
            "temperature": current.get("temperature_2m"),
            "apparent_temperature": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "precipitation": current.get("precipitation"),
            "wind_speed": current.get("wind_speed_10m"),
            "pressure": current.get("surface_pressure"),
            "timestamp": time.time(),
            "location": {
                "lat": float(LAT),
                "lon": float(LON)
            }
        }

        return weather

    except Exception as e:
        logger.error(f"Error fetching weather data: {e}")
        return None


def main():
    logger.info("Starting Weather Producer...")

    while True:
        data = fetch_weather()

        if data:
            producer.send(TOPIC, value=data)
            producer.flush()

            logger.info(
                f"Sent to Kafka | "
                f"temp={data['temperature']}°C, "
                f"feels_like={data['apparent_temperature']}°C, "
                f"humidity={data['humidity']}%, "
                f"rain={data['precipitation']}mm, "
                f"wind={data['wind_speed']}km/h, "
                f"pressure={data['pressure']}hPa"
            )

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()