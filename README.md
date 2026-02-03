# Battery Telemetry API

FastAPI service that ingests battery telemetry, stores it in PostgreSQL, and provides query APIs plus a background worker for offline device detection.

## Requirements

- Python 3.11+
- PostgreSQL (any recent version)

## Setup (local)

1. **Clone and create a virtual environment**

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate   # Linux/macOS
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**

   Copy `env.example` to `.env` and set `DATABASE_URL` for your PostgreSQL instance:

   ```
   DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/battery_telemetry
   ```

   Optional: `RATE_LIMIT_REQUESTS` (default 10), `RATE_LIMIT_WINDOW_SECONDS` (default 1).

4. **Create database and schema**

   Create the database, then apply the schema:

   ```bash
   psql -U postgres -c "CREATE DATABASE battery_telemetry;"
   psql -U postgres -d battery_telemetry -f schema.sql
   ```

   Grant sequence usage to your DB user if needed:

   ```sql
   GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO your_user;
   ```

## Run locally

- **API:** `uvicorn main:app --reload` (or `python -m uvicorn main:app --reload`)
- **Worker:** `python -m worker` (in a separate terminal)

API: http://127.0.0.1:8000  
Docs: http://127.0.0.1:8000/docs

## Docker

From the project root:

```bash
docker compose up --build
```

- Postgres: port 5432 (user/password/db from `docker-compose.yml`)
- API: http://localhost:8000
- Worker: runs in background; schema is applied on first start via init script

## API overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/telemetry` | Ingest telemetry (JSON body: device_id, timestamp, metrics) |
| GET | `/devices/{device_id}/metrics?start_time=&end_time=` | Time-series data (ISO 8601 range, max 8 days) |
| GET | `/devices/{device_id}/summary?date=YYYY-MM-DD` | Daily min/max/avg per metric |

Validation: device_id alphanumeric; metrics ranges (e.g. soc 0–100, voltage 200–500). Rate limit: 10 requests/second per device (429 when exceeded).

## Testing endpoints

**Health**
```bash
curl http://127.0.0.1:8000/health
```

**POST telemetry**
```bash
curl -X POST http://127.0.0.1:8000/telemetry -H "Content-Type: application/json" -d "{\"device_id\":\"test-001\",\"timestamp\":\"2026-02-01T14:23:45Z\",\"metrics\":{\"soc_percent\":67.5,\"voltage_v\":385.2,\"current_a\":-45.3,\"temp_c\":28.4}}"
```

**GET metrics**
```bash
curl "http://127.0.0.1:8000/devices/test-001/metrics?start_time=2026-02-01T00:00:00Z&end_time=2026-02-02T00:00:00Z"
```

**GET summary**
```bash
curl "http://127.0.0.1:8000/devices/test-001/summary?date=2026-02-01"
```

## Dependencies (main)

- fastapi >= 0.109.0
- uvicorn[standard] >= 0.27.0
- sqlalchemy >= 2.0.0
- asyncpg >= 0.29.0
- pydantic >= 2.5.0
- pydantic-settings >= 2.1.0

## Assumptions and limitations

- **PostgreSQL only** for the app (no SQLite fallback in this repo).
- **In-memory rate limiting** — per process; not shared across multiple API instances.
- **Worker** runs as a separate process; no distributed scheduler.
- **Metrics query** is limited to 8 days and 50,000 rows per request.
- **Summary** for a day with no data returns zeros for min/max/avg.

See [DESIGN.md](DESIGN.md) for schema rationale, scaling notes, and trade-offs.
