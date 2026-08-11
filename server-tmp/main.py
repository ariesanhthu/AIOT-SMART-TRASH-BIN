from __future__ import annotations

import json
import os
import secrets
import socket
import tempfile
import threading
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError


RESULT_LABELS: dict[int, str] = {
    0: "not_recognized",
    1: "plastic",
    2: "paper",
    3: "organic",
}
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DEVICE_TOKEN = "aiot-demo-token"
DEFAULT_MAX_IMAGE_BYTES = 1_500_000
DEFAULT_DEVICE_ID = "esp32cam-01"
DEFAULT_DEVICE_NAME = "Thùng rác ESP32-CAM"
DEFAULT_DEVICE_LOCATION = "Server local"
# Match Nano: FULL_THRESHOLD_HEIGHT_CM / BIN_HEIGHT_CM = 10 / 17 ≈ 59%.
DEFAULT_THRESHOLD = 0.59
LOCAL_TIMEZONE = ZoneInfo("Asia/Bangkok")
DETECTIONS_PATH = "/api/v1/detections"


class Probabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper: float = Field(ge=0.0, le=1.0)
    plastic: float = Field(ge=0.0, le=1.0)
    organic: float = Field(ge=0.0, le=1.0)


class FillLevels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plastic: int = Field(default=0, ge=0, le=100)
    paper: int = Field(default=0, ge=0, le=100)
    organic: int = Field(default=0, ge=0, le=100)


class DetectionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    received_at: datetime
    device_id: str
    result_code: int = Field(ge=0, le=3)
    waste_class: str
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: Probabilities
    inference_us: int = Field(ge=0)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    image_bytes: int = Field(gt=0)
    model_sha256: str | None = None
    firmware_version: str | None = None
    ai_model_version: str | None = None
    fill_levels: FillLevels = Field(default_factory=FillLevels)
    image_url: str


class HealthResponse(BaseModel):
    status: str
    stored_detections: int
    data_directory: str


class UpdateDeviceConfig(BaseModel):
    thresholds: dict[str, float] | None = None
    maintenanceMode: bool | None = None


class DetectionStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.images_dir = self.root / "images"
        self.metadata_dir = self.root / "metadata"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: DetectionRecord, image: bytes) -> DetectionRecord:
        image_path = self.images_dir / f"{record.id}.jpg"
        metadata_path = self.metadata_dir / f"{record.id}.json"

        self._atomic_write(image_path, image)
        try:
            metadata = json.dumps(
                record.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")
            self._atomic_write(metadata_path, metadata)
        except Exception:
            image_path.unlink(missing_ok=True)
            raise
        return record

    def get(self, detection_id: uuid.UUID) -> DetectionRecord | None:
        metadata_path = self.metadata_dir / f"{detection_id}.json"
        if not metadata_path.is_file():
            return None
        try:
            return DetectionRecord.model_validate_json(
                metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise RuntimeError(f"Corrupt metadata: {metadata_path.name}") from exc

    def list(self, limit: int | None = None) -> list[DetectionRecord]:
        records: list[DetectionRecord] = []
        for metadata_path in self.metadata_dir.glob("*.json"):
            try:
                records.append(
                    DetectionRecord.model_validate_json(
                        metadata_path.read_text(encoding="utf-8")
                    )
                )
            except (OSError, ValidationError, ValueError):
                continue
        records.sort(key=lambda item: item.received_at, reverse=True)
        return records if limit is None else records[:limit]

    def count(self) -> int:
        return sum(1 for _ in self.metadata_dir.glob("*.json"))

    def image_path(self, detection_id: uuid.UUID) -> Path | None:
        image_path = self.images_dir / f"{detection_id}.jpg"
        return image_path if image_path.is_file() else None

    @staticmethod
    def _atomic_write(destination: Path, content: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise


class LocalStateStore:
    """Small persistent store for dashboard configuration and alert state."""

    def __init__(self, root: Path) -> None:
        self.path = root / "dashboard_state.json"
        self._lock = threading.Lock()
        self.configs: dict[str, dict[str, object]] = {}
        self.resolved_alerts: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            self.configs = dict(content.get("configs", {}))
            self.resolved_alerts = dict(content.get("resolved_alerts", {}))
        except (OSError, TypeError, ValueError):
            self.configs = {}
            self.resolved_alerts = {}

    def get_config(self, device_id: str) -> dict[str, object]:
        with self._lock:
            stored = self.configs.get(device_id, {})
            thresholds = {
                "organic": DEFAULT_THRESHOLD,
                "paper": DEFAULT_THRESHOLD,
                "plastic": DEFAULT_THRESHOLD,
                **dict(stored.get("thresholds", {})),
            }
            return {
                "maintenanceMode": bool(stored.get("maintenanceMode", False)),
                "thresholds": thresholds,
            }

    def update_config(
        self, device_id: str, update: UpdateDeviceConfig
    ) -> dict[str, object]:
        with self._lock:
            current = self.configs.get(
                device_id,
                {
                    "maintenanceMode": False,
                    "thresholds": {
                        "organic": DEFAULT_THRESHOLD,
                        "paper": DEFAULT_THRESHOLD,
                        "plastic": DEFAULT_THRESHOLD,
                    },
                },
            )
            if update.thresholds is not None:
                thresholds = dict(current.get("thresholds", {}))
                for key, value in update.thresholds.items():
                    if key not in {"organic", "paper", "plastic"}:
                        raise ValueError(f"Unknown compartment: {key}")
                    if not 0.0 <= value <= 100.0:
                        raise ValueError("Threshold must be between 0 and 1 (or 0 and 100)")
                    thresholds[key] = value
                current["thresholds"] = thresholds
            if update.maintenanceMode is not None:
                current["maintenanceMode"] = update.maintenanceMode
            self.configs[device_id] = current
            self._persist_unlocked()
            return current

    def resolve_alert(self, event_id: str) -> dict[str, str]:
        with self._lock:
            resolution = {
                "resolvedAt": datetime.now(timezone.utc).isoformat(),
                "resolvedBy": "local-admin",
            }
            self.resolved_alerts[event_id] = resolution
            self._persist_unlocked()
            return resolution

    def get_resolution(self, event_id: str) -> dict[str, str] | None:
        with self._lock:
            return self.resolved_alerts.get(event_id)

    def _persist_unlocked(self) -> None:
        content = json.dumps(
            {
                "configs": self.configs,
                "resolved_alerts": self.resolved_alerts,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        DetectionStore._atomic_write(self.path, content)


def _threshold_percent(value: float) -> float:
    return value * 100.0 if value <= 1.0 else value


def _records_by_device(
    records: list[DetectionRecord], device_id: str
) -> list[DetectionRecord]:
    return [record for record in records if record.device_id == device_id]


def _classify_event(record: DetectionRecord) -> dict[str, object]:
    waste_type = (
        record.waste_class if record.result_code != 0 else "REJECTED"
    )
    target = record.waste_class if record.result_code != 0 else None
    timestamp = record.received_at.isoformat()
    return {
        "id": str(record.id),
        "eventType": "CLASSIFY",
        "wasteType": waste_type,
        "targetCompartment": target,
        "aiConfidence": record.confidence,
        "fillPercent": record.fill_levels.model_dump(),
        "alertThreshold": None,
        "deviceTimestamp": timestamp,
        "receivedAt": timestamp,
        "syncedLate": False,
        "firmwareVersion": record.firmware_version,
        "aiModelVersion": record.ai_model_version,
        "alertStatus": None,
        "resolvedAt": None,
        "resolvedBy": None,
        "imageUrl": record.image_url,
    }


def _full_alert_events(
    record: DetectionRecord, state: LocalStateStore
) -> list[dict[str, object]]:
    config = state.get_config(record.device_id)
    thresholds = dict(config["thresholds"])
    timestamp = record.received_at.isoformat()
    events: list[dict[str, object]] = []
    for compartment, fill in record.fill_levels.model_dump().items():
        threshold = float(thresholds.get(compartment, DEFAULT_THRESHOLD))
        if fill < _threshold_percent(threshold):
            continue
        event_id = f"{record.id}:{compartment}"
        resolution = state.get_resolution(event_id)
        events.append(
            {
                "id": event_id,
                "eventType": "FULL_ALERT",
                "wasteType": compartment,
                "targetCompartment": compartment,
                "aiConfidence": record.confidence,
                "fillPercent": record.fill_levels.model_dump(),
                "alertThreshold": threshold,
                "deviceTimestamp": timestamp,
                "receivedAt": timestamp,
                "syncedLate": False,
                "firmwareVersion": record.firmware_version,
                "aiModelVersion": record.ai_model_version,
                "alertStatus": "resolved" if resolution else "pending",
                "resolvedAt": resolution["resolvedAt"] if resolution else None,
                "resolvedBy": resolution["resolvedBy"] if resolution else None,
                "imageUrl": record.image_url,
            }
        )
    return events


def _full_alert_transitions(
    records: list[DetectionRecord], state: LocalStateStore
) -> list[dict[str, object]]:
    """Return one alert when a compartment crosses into FULL, not per image."""
    active = {"organic": False, "paper": False, "plastic": False}
    events: list[dict[str, object]] = []
    for record in reversed(records):
        candidates = {
            str(event["targetCompartment"]): event
            for event in _full_alert_events(record, state)
        }
        for compartment in active:
            is_full = compartment in candidates
            if is_full and not active[compartment]:
                events.append(candidates[compartment])
            active[compartment] = is_full
    events.reverse()
    return events


def _recognized_counts(records: list[DetectionRecord]) -> dict[str, int]:
    counts = {"organic": 0, "paper": 0, "plastic": 0}
    for record in records:
        if record.waste_class in counts:
            counts[record.waste_class] += 1
    return counts


def create_app(
    *,
    data_dir: Path | None = None,
    device_token: str | None = None,
    max_image_bytes: int | None = None,
) -> FastAPI:
    storage_dir = data_dir or Path(os.getenv("AIOT_DATA_DIR", DEFAULT_DATA_DIR))
    required_token = (
        device_token
        if device_token is not None
        else os.getenv("AIOT_DEVICE_TOKEN", DEFAULT_DEVICE_TOKEN)
    )
    image_limit = max_image_bytes or int(
        os.getenv("AIOT_MAX_IMAGE_BYTES", str(DEFAULT_MAX_IMAGE_BYTES))
    )
    if image_limit <= 0:
        raise ValueError("AIOT_MAX_IMAGE_BYTES must be positive")

    store = DetectionStore(storage_dir)
    dashboard_state = LocalStateStore(store.root)
    default_device_id = os.getenv("AIOT_DEFAULT_DEVICE_ID", DEFAULT_DEVICE_ID)
    application = FastAPI(
        title="AIoT Smart Trash Bin - Camera Receiver",
        version="1.0.0",
        description="Receives ESP32-CAM JPEG images and local AI results.",
    )
    application.state.store = store
    application.state.dashboard_state = dashboard_state
    application.state.device_token = required_token
    application.state.max_image_bytes = image_limit
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )

    @application.get("/", include_in_schema=False)
    def service_info() -> dict[str, str]:
        return {
            "service": "AIoT Smart Trash Bin camera receiver",
            "health": "/health",
            "docs": "/docs",
            "detections": DETECTIONS_PATH,
        }

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            stored_detections=store.count(),
            data_directory=str(store.root),
        )

    @application.post(
        DETECTIONS_PATH,
        response_model=DetectionRecord,
        status_code=status.HTTP_201_CREATED,
    )
    async def receive_detection(
        request: Request,
        result_code: Annotated[
            int, Header(alias="X-Result-Code", ge=0, le=3)
        ],
        confidence: Annotated[
            float, Header(alias="X-Confidence", ge=0.0, le=1.0)
        ],
        paper_probability: Annotated[
            float, Header(alias="X-Paper-Probability", ge=0.0, le=1.0)
        ],
        plastic_probability: Annotated[
            float, Header(alias="X-Plastic-Probability", ge=0.0, le=1.0)
        ],
        organic_probability: Annotated[
            float, Header(alias="X-Organic-Probability", ge=0.0, le=1.0)
        ],
        inference_us: Annotated[
            int, Header(alias="X-Inference-Us", ge=0)
        ],
        image_width: Annotated[
            int, Header(alias="X-Image-Width", gt=0)
        ],
        image_height: Annotated[
            int, Header(alias="X-Image-Height", gt=0)
        ],
        device_id: Annotated[
            str, Header(alias="X-Device-Id", min_length=1, max_length=64)
        ],
        image: Annotated[bytes, Body(media_type="image/jpeg")],
        device_token_header: Annotated[
            str | None, Header(alias="X-Device-Token")
        ] = None,
        model_sha256: Annotated[
            str | None, Header(alias="X-Model-Sha256", max_length=64)
        ] = None,
        firmware_version: Annotated[
            str | None, Header(alias="X-Firmware-Version", max_length=64)
        ] = None,
        ai_model_version: Annotated[
            str | None, Header(alias="X-Ai-Model-Version", max_length=128)
        ] = None,
        fill_plastic: Annotated[
            int, Header(alias="X-Fill-Plastic", ge=0, le=100)
        ] = 0,
        fill_paper: Annotated[
            int, Header(alias="X-Fill-Paper", ge=0, le=100)
        ] = 0,
        fill_organic: Annotated[
            int, Header(alias="X-Fill-Organic", ge=0, le=100)
        ] = 0,
    ) -> DetectionRecord:
        if required_token and (
            device_token_header is None
            or not secrets.compare_digest(device_token_header, required_token)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid device token",
            )

        content_type = request.headers.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != "image/jpeg":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Content-Type must be image/jpeg",
            )

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
            if declared_size > image_limit:
                raise HTTPException(status_code=413, detail="JPEG is too large")

        if not image:
            raise HTTPException(status_code=400, detail="JPEG body is empty")
        if len(image) > image_limit:
            raise HTTPException(status_code=413, detail="JPEG is too large")
        if not (image.startswith(b"\xff\xd8") and image.endswith(b"\xff\xd9")):
            raise HTTPException(status_code=400, detail="Invalid JPEG markers")

        probabilities = Probabilities(
            paper=paper_probability,
            plastic=plastic_probability,
            organic=organic_probability,
        )
        probability_sum = paper_probability + plastic_probability + organic_probability
        if probability_sum > 0.0 and not 0.98 <= probability_sum <= 1.02:
            raise HTTPException(
                status_code=422,
                detail="Class probabilities must sum to approximately 1",
            )

        detection_id = uuid.uuid4()
        record = DetectionRecord(
            id=detection_id,
            received_at=datetime.now(timezone.utc),
            device_id=device_id,
            result_code=result_code,
            waste_class=RESULT_LABELS[result_code],
            confidence=confidence,
            probabilities=probabilities,
            inference_us=inference_us,
            image_width=image_width,
            image_height=image_height,
            image_bytes=len(image),
            model_sha256=model_sha256,
            firmware_version=firmware_version,
            ai_model_version=ai_model_version,
            fill_levels=FillLevels(
                plastic=fill_plastic,
                paper=fill_paper,
                organic=fill_organic,
            ),
            image_url=f"{DETECTIONS_PATH}/{detection_id}/image",
        )
        try:
            return store.save(record, image)
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail="Unable to persist detection"
            ) from exc

    @application.get(
        DETECTIONS_PATH, response_model=list[DetectionRecord]
    )
    def list_detections(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> list[DetectionRecord]:
        return store.list(limit)

    @application.get(
        f"{DETECTIONS_PATH}/{{detection_id}}",
        response_model=DetectionRecord,
    )
    def get_detection(detection_id: uuid.UUID) -> DetectionRecord:
        try:
            record = store.get(detection_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Detection not found")
        return record

    @application.get(f"{DETECTIONS_PATH}/{{detection_id}}/image")
    def get_detection_image(detection_id: uuid.UUID) -> FileResponse:
        image_path = store.image_path(detection_id)
        if image_path is None:
            raise HTTPException(status_code=404, detail="Image not found")
        return FileResponse(
            image_path,
            media_type="image/jpeg",
            filename=f"{detection_id}.jpg",
            headers={"Cache-Control": "no-store"},
        )

    def device_response(device_id: str) -> dict[str, object]:
        records = _records_by_device(store.list(), device_id)
        latest = records[0] if records else None
        config = dashboard_state.get_config(device_id)
        thresholds = dict(config["thresholds"])
        fills = (
            latest.fill_levels.model_dump()
            if latest is not None
            else {"organic": 0, "paper": 0, "plastic": 0}
        )
        compartments: dict[str, dict[str, object]] = {}
        for key in ("organic", "paper", "plastic"):
            threshold = float(thresholds.get(key, DEFAULT_THRESHOLD))
            fill = int(fills.get(key, 0))
            compartments[key] = {
                "threshold": threshold,
                "fillPercent": fill,
                "status": (
                    "FULL"
                    if fill >= _threshold_percent(threshold)
                    else "AVAILABLE"
                ),
            }
        return {
            "deviceId": device_id,
            "name": os.getenv("AIOT_DEVICE_NAME", DEFAULT_DEVICE_NAME),
            "location": os.getenv(
                "AIOT_DEVICE_LOCATION", DEFAULT_DEVICE_LOCATION
            ),
            "lastSeenAt": latest.received_at.isoformat() if latest else None,
            "maintenanceMode": bool(config["maintenanceMode"]),
            "firmwareVersion": latest.firmware_version if latest else None,
            "aiModelVersion": latest.ai_model_version if latest else None,
            "className": "AIoT Smart Trash Bin",
            "compartments": compartments,
        }

    @application.get("/api/devices")
    def list_devices() -> list[dict[str, object]]:
        device_ids = {record.device_id for record in store.list()}
        device_ids.add(default_device_id)
        return [device_response(device_id) for device_id in sorted(device_ids)]

    @application.get("/api/devices/{device_id}")
    def get_device(device_id: str) -> dict[str, object]:
        known = device_id == default_device_id or any(
            record.device_id == device_id for record in store.list()
        )
        if not known:
            raise HTTPException(status_code=404, detail="Device not found")
        return device_response(device_id)

    @application.get("/api/devices/{device_id}/config")
    def get_device_config(device_id: str) -> dict[str, object]:
        config = dashboard_state.get_config(device_id)
        return {"deviceId": device_id, **config}

    @application.patch(
        "/api/devices/{device_id}/config", status_code=status.HTTP_204_NO_CONTENT
    )
    def update_device_config(
        device_id: str, update: UpdateDeviceConfig
    ) -> Response:
        try:
            dashboard_state.update_config(device_id, update)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Unable to save config") from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.get("/api/devices/{device_id}/events")
    def get_device_events(
        device_id: str,
        event_type: Annotated[str | None, Query(alias="eventType")] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[dict[str, object]]:
        records = _records_by_device(store.list(), device_id)
        if event_type == "CLASSIFY":
            events = [_classify_event(record) for record in records]
        elif event_type == "FULL_ALERT":
            events = _full_alert_transitions(records, dashboard_state)
        elif event_type is None:
            events = [_classify_event(record) for record in records]
            events.extend(_full_alert_transitions(records, dashboard_state))
            events.sort(key=lambda event: str(event["receivedAt"]), reverse=True)
        else:
            events = []
        return events[:limit]

    @application.patch(
        "/api/devices/{device_id}/events/{event_id}/resolve",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def resolve_alert(device_id: str, event_id: str) -> Response:
        del device_id
        try:
            dashboard_state.resolve_alert(event_id)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Unable to resolve alert") from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @application.get("/api/daily-stats")
    def daily_stats(
        device_id: Annotated[str, Query(alias="deviceId")],
        from_date: Annotated[date, Query(alias="from")],
        to_date: Annotated[date, Query(alias="to")],
    ) -> list[dict[str, object]]:
        if from_date > to_date:
            raise HTTPException(status_code=400, detail="from must not be after to")
        records = _records_by_device(store.list(), device_id)
        per_day: dict[date, list[DetectionRecord]] = defaultdict(list)
        for record in records:
            local_date = record.received_at.astimezone(LOCAL_TIMEZONE).date()
            if from_date <= local_date <= to_date:
                per_day[local_date].append(record)
        response: list[dict[str, object]] = []
        current = from_date
        while current <= to_date:
            counts = _recognized_counts(per_day[current])
            total = sum(counts.values())
            response.append(
                {
                    "deviceId": device_id,
                    "date": current.isoformat(),
                    "organicCount": counts["organic"],
                    "paperCount": counts["paper"],
                    "plasticCount": counts["plastic"],
                    "totalCount": total,
                }
            )
            current += timedelta(days=1)
        return response

    def records_for_recent_days(days: int) -> list[DetectionRecord]:
        if days < 1 or days > 3650:
            raise HTTPException(status_code=422, detail="days must be between 1 and 3650")
        today = datetime.now(LOCAL_TIMEZONE).date()
        first_date = today - timedelta(days=days - 1)
        return [
            record
            for record in store.list()
            if record.received_at.astimezone(LOCAL_TIMEZONE).date() >= first_date
        ]

    @application.get("/api/daily-stats/summary")
    def daily_stats_summary(
        days: Annotated[int, Query(ge=1, le=3650)] = 1,
    ) -> dict[str, object]:
        counts = _recognized_counts(records_for_recent_days(days))
        total = sum(counts.values())
        return {
            "date": datetime.now(LOCAL_TIMEZONE).date().isoformat(),
            "organicCount": counts["organic"],
            "paperCount": counts["paper"],
            "plasticCount": counts["plastic"],
            "recyclableCount": counts["paper"] + counts["plastic"],
            "totalCount": total,
        }

    @application.get("/api/daily-stats/ranking")
    def daily_stats_ranking(
        days: Annotated[int, Query(ge=1, le=3650)] = 7,
    ) -> list[dict[str, object]]:
        counts: dict[str, int] = defaultdict(int)
        for record in records_for_recent_days(days):
            if record.result_code != 0:
                counts[record.device_id] += 1
        return [
            {"deviceId": device_id, "totalCount": total}
            for device_id, total in sorted(
                counts.items(), key=lambda item: item[1], reverse=True
            )
        ]

    return application


app = create_app()


def _detect_outbound_ipv4() -> str | None:
    """Return the IPv4 address used by the default route without sending data."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            return str(probe.getsockname()[0])
    except OSError:
        return None


if __name__ == "__main__":
    bind_host = os.getenv("AIOT_HOST", "0.0.0.0")
    bind_port = int(os.getenv("AIOT_PORT", "8000"))
    advertised_host = os.getenv("AIOT_ADVERTISE_HOST")
    if not advertised_host:
        advertised_host = (
            _detect_outbound_ipv4()
            if bind_host in {"0.0.0.0", ""}
            else bind_host
        )
    if advertised_host:
        print(
            "ESP telemetry URL: "
            f"http://{advertised_host}:{bind_port}{DETECTIONS_PATH}",
            flush=True,
        )
    else:
        print(
            "Unable to detect LAN IPv4; inspect ipconfig and update "
            "ESP-TRASH/network_config.h",
            flush=True,
        )
    uvicorn.run(
        "main:app",
        host=bind_host,
        port=bind_port,
        reload=False,
    )
