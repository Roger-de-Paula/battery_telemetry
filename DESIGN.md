# Design Document

## Database schema

**Tables**

- **devices** — One row per device: `device_id` (PK), `last_seen`, `status`. Updated on every telemetry POST so the worker can find devices with no recent data.
- **telemetry** — Time-series: `device_id`, `timestamp`, and four metrics (soc_percent, voltage_v, current_a, temp_c). FK to devices with CASCADE delete.
- **alerts** — One row per offline event: `device_id`, `detected_at`, `last_seen`. Used for logging and for deduplication (avoid re-alerting the same offline period).

**Indexing**

- `idx_telemetry_device_timestamp` on `(device_id, timestamp DESC)` so range queries by device and time use the index and stay efficient for 7-day windows.
- `idx_alerts_device_detected` on `(device_id, detected_at DESC)` for “latest alert per device” in the worker.

**When to partition**

Partition the telemetry table by time (e.g. by month) when:

- Row count per device grows large (e.g. hundreds of thousands per device), or
- You need to drop or archive old data by range.

Partitioning by `timestamp` (e.g. LIST/RANGE by month) keeps 7-day queries on a small set of partitions. Without partitioning, the single index on `(device_id, timestamp)` is sufficient for moderate scale.

**High write throughput**

- Use connection pooling (SQLAlchemy’s default pool is fine; tune `pool_size` / `max_overflow` if needed).
- For very high ingest, consider batching inserts (e.g. bulk insert every N seconds) and/or async write buffers; the current design is one insert per request for simplicity.

---

## Rate limiting

- **Approach:** In-memory sliding window per `device_id`: keep timestamps of recent requests; if count in the last 1 second ≥ 10, return 429.
- **Trade-offs:** No extra infra (no Redis), but state is per process. With multiple API replicas, each has its own window, so effective limit is 10 × number of replicas per device. For a single instance or low replica count this is acceptable.
- **Scaling:** For strict “10 req/s per device” across replicas, use a shared store (e.g. Redis) with the same window logic.

---

## Background worker

- **Design:** Single process, asyncio loop: every 5 minutes it selects devices with `last_seen` older than 10 minutes, logs an alert, and inserts into `alerts`. Deduplication: if the latest alert for that device has the same `last_seen` (within 60 s), skip to avoid duplicate alerts for the same offline period.
- **Deployment:** Run as a separate container/process; no Celery. Sufficient for one-off checks; for many devices or more complex scheduling, a task queue (Celery, RQ) would scale better.

---

## Scaling 10 → 10,000 devices

- **API:** Horizontal scaling: multiple uvicorn workers or replicas behind a load balancer. Move rate limiting to Redis if you need a single global limit per device.
- **Database:** Connection pooling; consider read replicas for GET metrics/summary if read load grows. Ensure the telemetry index `(device_id, timestamp)` is in place; add partitioning by time if telemetry volume is large.
- **Worker:** One worker can handle 10k devices if the “offline” query and alert inserts stay fast. For more devices or heavier logic, shard by device_id or use a queue so multiple workers can consume work.
- **Storage:** Monitor telemetry table size; archive or drop old partitions as needed.

---

## One production concern

**Database connection exhaustion under load.** Many concurrent requests each hold a session until the request ends. With high concurrency and a small pool, requests can block waiting for a connection. Mitigations: tune `pool_size` and `max_overflow`, use async consistently, and consider a read replica for read-heavy endpoints so write connections are not starved.

---

## What we’d improve with more time

- **Tests:** API tests are in place (pytest, in-memory SQLite): health, ingestion, validation, 404s, time range, summary with/without data, rate limit. Worker tests (offline detection and deduplication) could be added.
- **Structured logging:** Request IDs, JSON logs, and log levels for production.
- **Configurable worker interval and threshold** via env (e.g. check every 1 min, offline after 5 min).
- **Redis rate limiting** for multi-instance deployments.
- **OpenAPI tags and examples** for clearer docs.
- **Health check** that verifies DB connectivity (e.g. simple SELECT) so orchestration can detect DB outages.
