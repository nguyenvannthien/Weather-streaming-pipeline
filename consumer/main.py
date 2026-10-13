import os
import psycopg2
from psycopg2.extras import execute_values
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, avg, window
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType

#doc file env cau hinh 
AGGREGATION_WINDOW = os.getenv("AGGREGATION_WINDOW", "2 minutes")
SPARK_TRIGGER_INTERVAL = os.getenv("SPARK_TRIGGER_INTERVAL", "2 minutes")

#ham ghi du lieu vao postgres
def write_to_postgres(batch_df, batch_id):
    postgres_host = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port = os.getenv("POSTGRES_PORT", "5432")
    postgres_db = os.getenv("POSTGRES_DB", "weather_db")
    postgres_user = os.getenv("POSTGRES_USER", "weather_user")
    postgres_password = os.getenv("POSTGRES_PASSWORD", "weather_password")

    rows = batch_df.select(
        col("window.start").alias("window_start"),
        col("window.end").alias("window_end"),
        col("avg_temperature"),
        col("avg_feels_like"),
        col("avg_humidity"),
        col("avg_precipitation"),
        col("avg_wind_speed"),
        col("avg_pressure"),
    ).collect() #chuyen DF sang List

    if not rows:
        print(f"Batch {batch_id} has no rows to write")
        return

    conn = psycopg2.connect(
        host=postgres_host,
        port=postgres_port,
        database=postgres_db,
        user=postgres_user,
        password=postgres_password,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
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
                    UNIQUE (window_start, window_end)
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weather_stats_window_start
                ON weather_stats(window_start DESC);
                """
            )
            cur.execute(
                """
                DELETE FROM weather_stats a
                USING weather_stats b
                WHERE a.id < b.id
                  AND a.window_start = b.window_start
                  AND a.window_end = b.window_end;
                """
            )
            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'weather_stats_window_unique'
                    ) THEN
                        ALTER TABLE weather_stats
                        ADD CONSTRAINT weather_stats_window_unique
                        UNIQUE (window_start, window_end);
                    END IF;
                END $$;
                """
            )
            execute_values(
                cur,
                """
                INSERT INTO weather_stats (
                    window_start,
                    window_end,
                    avg_temperature,
                    avg_feels_like,
                    avg_humidity,
                    avg_precipitation,
                    avg_wind_speed,
                    avg_pressure
                )
                VALUES %s
                ON CONFLICT (window_start, window_end) DO UPDATE SET
                    avg_temperature = EXCLUDED.avg_temperature,
                    avg_feels_like = EXCLUDED.avg_feels_like,
                    avg_humidity = EXCLUDED.avg_humidity,
                    avg_precipitation = EXCLUDED.avg_precipitation,
                    avg_wind_speed = EXCLUDED.avg_wind_speed,
                    avg_pressure = EXCLUDED.avg_pressure,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                [tuple(row) for row in rows],
            )
        conn.commit()
    finally:
        conn.close()

    print(f"Batch {batch_id} upserted {len(rows)} rows to PostgreSQL")


def main():
    # 1. Khoi tao Session
    spark = SparkSession.builder \
        .appName("WeatherStreamingConsumer") \
        .config(
            "spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0"
        ) \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")

    # 2. Tao schema data json tu kafka
    schema = StructType([
        StructField("time", StringType()),
        StructField("temperature", DoubleType()),
        StructField("apparent_temperature", DoubleType()),
        StructField("humidity", DoubleType()),
        StructField("precipitation", DoubleType()),
        StructField("wind_speed", DoubleType()),
        StructField("pressure", DoubleType()),
        StructField("timestamp", DoubleType())
    ])

    # 3. doc data do ve tu kafka
    kafka_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    topic = os.getenv("WEATHER_TOPIC", "weather_data")

    df = spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", kafka_bootstrap_servers) \
        .option("subscribe", topic) \
        .option("group.id", "weather-consumer-group") \
        .option("kafka.group.id", "weather-consumer-group") \
        .option("startingOffsets", "earliest") \
        .load()

    # 4. Parse kieu data Byte > string
    weather_df = df.selectExpr("CAST(value AS STRING)") \
        .select(from_json(col("value"), schema).alias("data")) \
        .select("data.*") \
        .withColumn("event_time", col("timestamp").cast(TimestampType()))

    # 5. Window aggregation
    weather_stats_df = weather_df \
        .withWatermark("event_time", "10 minutes") \
        .groupBy(window(col("event_time"), AGGREGATION_WINDOW)) \
        .agg(
            avg("temperature").alias("avg_temperature"),
            avg("apparent_temperature").alias("avg_feels_like"),
            avg("humidity").alias("avg_humidity"),
            avg("precipitation").alias("avg_precipitation"),
            avg("wind_speed").alias("avg_wind_speed"),
            avg("pressure").alias("avg_pressure")
        )

    # 6. in console de debug
    console_query = weather_stats_df.writeStream \
        .outputMode("update") \
        .format("console") \
        .option("truncate", "false") \
        .option("checkpointLocation", "/tmp/checkpoints/weather_stats_console") \
        .trigger(processingTime=SPARK_TRIGGER_INTERVAL) \
        .start()

    # 7. To Postgres
    postgres_query = weather_stats_df.writeStream \
        .outputMode("update") \
        .foreachBatch(write_to_postgres) \
        .option("checkpointLocation", "/tmp/checkpoints/weather_stats_postgres") \
        .trigger(processingTime=SPARK_TRIGGER_INTERVAL) \
        .start()

    console_query.awaitTermination()
    postgres_query.awaitTermination()


if __name__ == "__main__":
    main()
