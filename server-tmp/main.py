from __future__ import annotations

import json
import os
import secrets
import socket
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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
DETECTIONS_PATH = "/api/v1/detections"


class Probabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper: float = Field(ge=0.0, le=1.0)
    plastic: float = Field(ge=0.0, le=1.0)
    organic: float = Field(ge=0.0, le=1.0)


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
    image_url: str


class HealthResponse(BaseModel):
    status: str
    stored_detections: int
    data_directory: str


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

    def list(self, limit: int) -> list[DetectionRecord]:
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
        return records[:limit]

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
    application = FastAPI(
        title="AIoT Smart Trash Bin - Camera Receiver",
        version="1.0.0",
        description="Receives ESP32-CAM JPEG images and local AI results.",
    )
    application.state.store = store
    application.state.device_token = required_token
    application.state.max_image_bytes = image_limit
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
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
