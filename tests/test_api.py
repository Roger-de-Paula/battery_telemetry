"""API tests."""


def test_health(client):
    """GET /health returns 200 and status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_post_telemetry_valid_then_get_metrics(client):
    """POST valid telemetry then GET metrics returns the stored point."""
    body = {
        "device_id": "test-001",
        "timestamp": "2026-02-01T14:23:45Z",
        "metrics": {
            "soc_percent": 67.5,
            "voltage_v": 385.2,
            "current_a": -45.3,
            "temp_c": 28.4,
        },
    }
    post = client.post("/telemetry", json=body)
    assert post.status_code == 201
    assert post.json() == {"status": "created"}

    get_metrics = client.get(
        "/devices/test-001/metrics",
        params={
            "start_time": "2026-02-01T00:00:00Z",
            "end_time": "2026-02-02T00:00:00Z",
        },
    )
    assert get_metrics.status_code == 200
    data = get_metrics.json()
    assert data["device_id"] == "test-001"
    assert len(data["data"]) == 1
    row = data["data"][0]
    assert row["soc_percent"] == 67.5
    assert row["voltage_v"] == 385.2
    assert row["current_a"] == -45.3
    assert row["temp_c"] == 28.4
    assert "2026-02-01" in row["timestamp"] and "14:23:45" in row["timestamp"]


def test_post_telemetry_validation_fails(client):
    """POST with invalid body returns 400 and structured error response."""
    base = {
        "device_id": "test-001",
        "timestamp": "2026-02-01T14:23:45Z",
        "metrics": {
            "soc_percent": 67.5,
            "voltage_v": 385.2,
            "current_a": -45.3,
            "temp_c": 28.4,
        },
    }
    # Invalid device_id (non-alphanumeric)
    bad_device = {**base, "device_id": "bad id!"}
    r = client.post("/telemetry", json=bad_device)
    assert r.status_code == 400
    body = r.json()
    assert "detail" in body
    assert body.get("errors") is not None
    assert any("device_id" in str(e.get("loc", [])) for e in body["errors"])

    # Out-of-range metric (soc_percent > 100)
    bad_soc = {**base, "metrics": {**base["metrics"], "soc_percent": 150}}
    r2 = client.post("/telemetry", json=bad_soc)
    assert r2.status_code == 400
    body2 = r2.json()
    assert "detail" in body2
    assert body2.get("errors") is not None


def test_get_metrics_device_not_found(client):
    """GET /devices/{id}/metrics returns 404 when device does not exist."""
    response = client.get(
        "/devices/nonexistent-99/metrics",
        params={
            "start_time": "2026-02-01T00:00:00Z",
            "end_time": "2026-02-02T00:00:00Z",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Device not found"


def test_get_summary_device_not_found(client):
    """GET /devices/{id}/summary returns 404 when device does not exist."""
    response = client.get(
        "/devices/nonexistent-99/summary",
        params={"date": "2026-02-01"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Device not found"


def test_get_metrics_bad_time_range(client):
    """GET /devices/{id}/metrics returns 400 when start_time > end_time or range > 8 days."""
    # Create device first so we hit the time validation, not 404
    client.post(
        "/telemetry",
        json={
            "device_id": "t-range",
            "timestamp": "2026-02-01T12:00:00Z",
            "metrics": {"soc_percent": 50, "voltage_v": 400, "current_a": 0, "temp_c": 25},
        },
    )
    # start_time after end_time
    r = client.get(
        "/devices/t-range/metrics",
        params={
            "start_time": "2026-02-02T00:00:00Z",
            "end_time": "2026-02-01T00:00:00Z",
        },
    )
    assert r.status_code == 400
    assert "start_time" in r.json()["detail"].lower() or "before" in r.json()["detail"].lower()

    # Range > 8 days
    r2 = client.get(
        "/devices/t-range/metrics",
        params={
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-15T00:00:00Z",
        },
    )
    assert r2.status_code == 400
    assert "8" in r2.json()["detail"] or "days" in r2.json()["detail"].lower()


def test_get_summary_with_data(client):
    """GET /devices/{id}/summary returns min/max/avg for the day when data exists."""
    device_id = "summary-dev"
    for i, (soc, ts) in enumerate([(20.0, "08:00:00"), (50.0, "12:00:00"), (80.0, "18:00:00")]):
        client.post(
            "/telemetry",
            json={
                "device_id": device_id,
                "timestamp": f"2026-02-01T{ts}Z",
                "metrics": {"soc_percent": soc, "voltage_v": 380 + i * 10, "current_a": -5.0, "temp_c": 22.0 + i},
            },
        )
    response = client.get(
        f"/devices/{device_id}/summary",
        params={"date": "2026-02-01"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == device_id
    assert data["date"] == "2026-02-01"
    s = data["summary"]
    assert s["soc_percent"]["min"] == 20.0
    assert s["soc_percent"]["max"] == 80.0
    assert s["soc_percent"]["avg"] == 50.0
    assert s["voltage_v"]["min"] == 380.0
    assert s["voltage_v"]["max"] == 400.0
    assert s["temp_c"]["min"] == 22.0
    assert s["temp_c"]["max"] == 24.0


def test_get_summary_no_data_for_day(client):
    """GET /devices/{id}/summary returns zeros when device exists but has no data for the day."""
    client.post(
        "/telemetry",
        json={
            "device_id": "empty-day",
            "timestamp": "2026-02-02T12:00:00Z",
            "metrics": {"soc_percent": 50, "voltage_v": 400, "current_a": 0, "temp_c": 25},
        },
    )
    response = client.get(
        "/devices/empty-day/summary",
        params={"date": "2026-02-01"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == "empty-day"
    assert data["date"] == "2026-02-01"
    for metric in ("soc_percent", "voltage_v", "current_a", "temp_c"):
        assert data["summary"][metric]["min"] == 0
        assert data["summary"][metric]["max"] == 0
        assert data["summary"][metric]["avg"] == 0


def test_rate_limit_exceeds_per_device(client):
    """POST /telemetry returns 429 when device exceeds rate limit (10/sec)."""
    body = {
        "device_id": "rate-limit-dev",
        "timestamp": "2026-02-01T14:23:45Z",
        "metrics": {"soc_percent": 50, "voltage_v": 400, "current_a": 0, "temp_c": 25},
    }
    for _ in range(10):
        r = client.post("/telemetry", json=body)
        assert r.status_code == 201
    r11 = client.post("/telemetry", json=body)
    assert r11.status_code == 429
    assert "rate limit" in r11.json()["detail"].lower()
