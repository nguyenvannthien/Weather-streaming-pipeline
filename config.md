2. kafka_consumergroup_lag
3. kafka_brokers
1. kafka_topic_partition_current_offset
4. rate(kafka_topic_partition_current_offset[1m])

docker exec -it weather-postgres psql -U weather_user -d weather_db
\dt
SELECT * FROM weather_stats
ORDER BY id DESC
LIMIT 100;

SELECT * FROM weather_stats
ORDER BY id DESC;