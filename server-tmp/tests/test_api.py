from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app  # noqa: E402


JPEG = b"\xff\xd8test-jpeg-data\xff\xd9"


def detection_headers(token: str = "test-token") -> dict[str, str]:
    return {
        "Content-Type": "image/jpeg",
        "X-Device-Token": token,
        "X-Device-Id": "esp32cam-01",
        "X-Result-Code": "1",
        "X-Confidence": "0.8",
        "X-Paper-Probability": "0.1",
        "X-Plastic-Probability": "0.8",
        "X-Organic-Probability": "0.1",
        "X-Inference-Us": "12345",
        "X-Image-Width": "320",
        "X-Image-Height": "240",
        "X-Model-Sha256": "a" * 64,
        "X-Firmware-Version": "v5.0-local-python-server",
        "X-Ai-Model-Version": "tinycnn-test",
        "X-Fill-Plastic": "81",
        "X-Fill-Paper": "20",
        "X-Fill-Organic": "30",
    }


def test_receive_list_and_read_image(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, device_token="test-token")
    client = TestClient(app)

    response = client.post(
        "/api/v1/detections",
        content=JPEG,
        headers=detection_headers(),
    )
    assert response.status_code == 201
    record = response.json()
    assert record["result_code"] == 1
    assert record["waste_class"] == "plastic"
    assert record["image_bytes"] == len(JPEG)
    assert record["fill_levels"]["plastic"] == 81

    listing = client.get("/api/v1/detections")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [record["id"]]

    image_response = client.get(record["image_url"])
    assert image_response.status_code == 200
    assert image_response.content == JPEG
    assert image_response.headers["content-type"] == "image/jpeg"


def test_frontend_compatible_endpoints(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, device_token="test-token")
    client = TestClient(app)
    created = client.post(
        "/api/v1/detections",
        content=JPEG,
        headers=detection_headers(),
    ).json()

    devices = client.get("/api/devices")
    assert devices.status_code == 200
    device = next(
        item for item in devices.json() if item["deviceId"] == "esp32cam-01"
    )
    assert device["compartments"]["plastic"]["fillPercent"] == 81

    classify = client.get(
        "/api/devices/esp32cam-01/events?eventType=CLASSIFY&limit=20"
    )
    assert classify.status_code == 200
    assert classify.json()[0]["imageUrl"] == created["image_url"]

    alerts = client.get(
        "/api/devices/esp32cam-01/events?eventType=FULL_ALERT&limit=20"
    )
    assert alerts.status_code == 200
    assert alerts.json()[0]["targetCompartment"] == "plastic"
    alert_id = alerts.json()[0]["id"]
    assert client.patch(
        f"/api/devices/esp32cam-01/events/{alert_id}/resolve", json={}
    ).status_code == 204
    assert client.get(
        "/api/devices/esp32cam-01/events?eventType=FULL_ALERT&limit=20"
    ).json()[0]["alertStatus"] == "resolved"

    summary = client.get("/api/daily-stats/summary?days=1")
    assert summary.status_code == 200
    assert summary.json()["plasticCount"] == 1

    ranking = client.get("/api/daily-stats/ranking?days=7")
    assert ranking.status_code == 200
    assert ranking.json() == [{"deviceId": "esp32cam-01", "totalCount": 1}]

    config = client.patch(
        "/api/devices/esp32cam-01/config",
        json={"thresholds": {"plastic": 0.9}, "maintenanceMode": True},
    )
    assert config.status_code == 204
    loaded_config = client.get("/api/devices/esp32cam-01/config").json()
    assert loaded_config["maintenanceMode"] is True
    assert loaded_config["thresholds"]["plastic"] == 0.9


def test_rejects_bad_token(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, device_token="test-token")
    client = TestClient(app)
    response = client.post(
        "/api/v1/detections",
        content=JPEG,
        headers=detection_headers(token="wrong-token"),
    )
    assert response.status_code == 401


def test_rejects_invalid_jpeg(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, device_token="test-token")
    client = TestClient(app)
    response = client.post(
        "/api/v1/detections",
        content=b"not-a-jpeg",
        headers=detection_headers(),
    )
    assert response.status_code == 400


def test_full_alert_is_created_only_on_threshold_crossing(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, device_token="test-token")
    client = TestClient(app)

    for _ in range(2):
        response = client.post(
            "/api/v1/detections",
            content=JPEG,
            headers=detection_headers(),
        )
        assert response.status_code == 201

    alerts = client.get(
        "/api/devices/esp32cam-01/events?eventType=FULL_ALERT&limit=20"
    )
    assert alerts.status_code == 200
    plastic_alerts = [
        event
        for event in alerts.json()
        if event["targetCompartment"] == "plastic"
    ]
    assert len(plastic_alerts) == 1
