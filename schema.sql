-- Battery telemetry schema
-- Run this against your PostgreSQL database to create tables and indexes.

-- Device metadata: last_seen and status for offline detection
CREATE TABLE IF NOT EXISTS devices (
    device_id VARCHAR(64) PRIMARY KEY,
    last_seen TIMESTAMPTZ NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'online'
);

-- Telemetry time-series: one row per sample per device
CREATE TABLE IF NOT EXISTS telemetry (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(64) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    soc_percent NUMERIC(5, 2) NOT NULL,
    voltage_v NUMERIC(6, 2) NOT NULL,
    current_a NUMERIC(6, 2) NOT NULL,
    temp_c NUMERIC(4, 2) NOT NULL
);

-- Index for efficient 7-day range queries by device
CREATE INDEX IF NOT EXISTS idx_telemetry_device_timestamp
    ON telemetry (device_id, timestamp DESC);

-- Offline alerts: one row per detected offline event (avoids duplicate alerts)
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    device_id VARCHAR(64) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    detected_at TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_device_detected
    ON alerts (device_id, detected_at DESC);
