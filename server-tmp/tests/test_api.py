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

    listing = client.get("/api/v1/detections")
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [record["id"]]

    image_response = client.get(record["image_url"])
    assert image_response.status_code == 200
    assert image_response.content == JPEG
    assert image_response.headers["content-type"] == "image/jpeg"


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
