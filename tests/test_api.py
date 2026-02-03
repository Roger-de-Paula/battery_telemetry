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
