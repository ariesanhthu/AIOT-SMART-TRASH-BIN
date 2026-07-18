import { useEffect, useRef, useState } from "react";

type StreamStatus = "connecting" | "live" | "error";

type CapturedImage = {
  id: string;
  blob: Blob;
  url: string;
  fileName: string;
  capturedAt: string;
  size: number;
};

type ZipFile = {
  name: string;
  data: Uint8Array<ArrayBuffer>;
};

const trimTrailingSlash = (value: string) => value.replace(/\/$/, "");
const captureBaseUrl = trimTrailingSlash(
  import.meta.env.VITE_ESP32_CAMERA_URL?.trim() || "",
);
const streamBaseUrl = trimTrailingSlash(
  import.meta.env.VITE_ESP32_STREAM_URL?.trim() || "",
);

const streamStatusText: Record<StreamStatus, string> = {
  connecting: "Đang kết nối",
  live: "Trực tiếp",
  error: "Mất kết nối",
};

const formatTimestampForFile = (date: Date) =>
  date.toISOString().replaceAll(":", "-").replaceAll(".", "-");

const formatFileSize = (size: number) => {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};

const crcTable = (() => {
  const table = new Uint32Array(256);

  for (let i = 0; i < 256; i += 1) {
    let value = i;
    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    table[i] = value >>> 0;
  }

  return table;
})();

const calculateCrc32 = (data: Uint8Array<ArrayBuffer>) => {
  let crc = 0xffffffff;

  for (const byte of data) {
    crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }

  return (crc ^ 0xffffffff) >>> 0;
};

const createHeader = (size: number) => {
  const bytes = new Uint8Array(size);
  return {
    bytes,
    view: new DataView(bytes.buffer),
  };
};

const createZipBlob = (files: ZipFile[]) => {
  const encoder = new TextEncoder();
  const chunks: BlobPart[] = [];
  const centralDirectoryChunks: BlobPart[] = [];
  let offset = 0;

  for (const file of files) {
    const nameBytes = encoder.encode(file.name);
    const crc32 = calculateCrc32(file.data);
    const localHeader = createHeader(30);

    localHeader.view.setUint32(0, 0x04034b50, true);
    localHeader.view.setUint16(4, 20, true);
    localHeader.view.setUint16(6, 0x0800, true);
    localHeader.view.setUint16(8, 0, true);
    localHeader.view.setUint16(10, 0, true);
    localHeader.view.setUint16(12, 0, true);
    localHeader.view.setUint32(14, crc32, true);
    localHeader.view.setUint32(18, file.data.byteLength, true);
    localHeader.view.setUint32(22, file.data.byteLength, true);
    localHeader.view.setUint16(26, nameBytes.byteLength, true);
    localHeader.view.setUint16(28, 0, true);

    chunks.push(localHeader.bytes, nameBytes, file.data);

    const centralHeader = createHeader(46);
    centralHeader.view.setUint32(0, 0x02014b50, true);
    centralHeader.view.setUint16(4, 20, true);
    centralHeader.view.setUint16(6, 20, true);
    centralHeader.view.setUint16(8, 0x0800, true);
    centralHeader.view.setUint16(10, 0, true);
    centralHeader.view.setUint16(12, 0, true);
    centralHeader.view.setUint16(14, 0, true);
    centralHeader.view.setUint32(16, crc32, true);
    centralHeader.view.setUint32(20, file.data.byteLength, true);
    centralHeader.view.setUint32(24, file.data.byteLength, true);
    centralHeader.view.setUint16(28, nameBytes.byteLength, true);
    centralHeader.view.setUint16(30, 0, true);
    centralHeader.view.setUint16(32, 0, true);
    centralHeader.view.setUint16(34, 0, true);
    centralHeader.view.setUint16(36, 0, true);
    centralHeader.view.setUint32(38, 0, true);
    centralHeader.view.setUint32(42, offset, true);

    centralDirectoryChunks.push(centralHeader.bytes, nameBytes);
    offset += localHeader.bytes.byteLength + nameBytes.byteLength + file.data.byteLength;
  }

  const centralDirectorySize = centralDirectoryChunks.reduce(
    (total, chunk) => total + (chunk instanceof Uint8Array ? chunk.byteLength : 0),
    0,
  );
  const endHeader = createHeader(22);

  endHeader.view.setUint32(0, 0x06054b50, true);
  endHeader.view.setUint16(4, 0, true);
  endHeader.view.setUint16(6, 0, true);
  endHeader.view.setUint16(8, files.length, true);
  endHeader.view.setUint16(10, files.length, true);
  endHeader.view.setUint32(12, centralDirectorySize, true);
  endHeader.view.setUint32(16, offset, true);
  endHeader.view.setUint16(20, 0, true);

  return new Blob([...chunks, ...centralDirectoryChunks, endHeader.bytes], {
    type: "application/zip",
  });
};

const triggerDownload = (href: string, fileName: string) => {
  const downloadLink = document.createElement("a");
  downloadLink.href = href;
  downloadLink.download = fileName;
  document.body.appendChild(downloadLink);
  downloadLink.click();
  downloadLink.remove();
};

export default function EspCamera() {
  const [capturedImages, setCapturedImages] = useState<CapturedImage[]>([]);
  const [isCapturing, setIsCapturing] = useState(false);
  const [isDownloadingAll, setIsDownloadingAll] = useState(false);
  const [message, setMessage] = useState("");
  const [streamKey, setStreamKey] = useState(() => Date.now());
  const [streamStatus, setStreamStatus] =
    useState<StreamStatus>("connecting");

  const capturedImagesRef = useRef<CapturedImage[]>([]);
  const captureAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      captureAbortRef.current?.abort();
      captureAbortRef.current = null;

      for (const image of capturedImagesRef.current) {
        URL.revokeObjectURL(image.url);
      }
      capturedImagesRef.current = [];
    };
  }, []);

  const updateCapturedImages = (
    updater: (images: CapturedImage[]) => CapturedImage[],
  ) => {
    setCapturedImages((currentImages) => {
      const nextImages = updater(currentImages);
      capturedImagesRef.current = nextImages;
      return nextImages;
    });
  };

  const captureImage = async () => {
    const controller = new AbortController();
    captureAbortRef.current = controller;
    setIsCapturing(true);
    setMessage("Đang chụp ảnh...");

    try {
      const response = await fetch(
        `${captureBaseUrl}/capture?time=${Date.now()}`,
        {
          method: "GET",
          cache: "no-store",
          headers: { Accept: "image/jpeg" },
          signal: controller.signal,
        },
      );

      if (!response.ok) {
        const detail = (await response.text()).trim();
        throw new Error(
          detail
            ? `ESP32-CAM trả về HTTP ${response.status}: ${detail}`
            : `ESP32-CAM trả về HTTP ${response.status}`,
        );
      }

      const contentType = response.headers.get("content-type") ?? "";
      if (!contentType.toLowerCase().includes("image/jpeg")) {
        throw new Error(`Dữ liệu trả về không phải JPEG: ${contentType}`);
      }

      const imageBlob = await response.blob();
      if (imageBlob.size === 0) {
        throw new Error("ESP32-CAM trả về ảnh rỗng");
      }

      const capturedAt = new Date();
      const imageUrl = URL.createObjectURL(imageBlob);
      const capturedImage: CapturedImage = {
        id: `${capturedAt.getTime()}-${imageBlob.size}`,
        blob: imageBlob,
        url: imageUrl,
        fileName: `esp32-cam-${formatTimestampForFile(capturedAt)}.jpg`,
        capturedAt: capturedAt.toLocaleString("vi-VN"),
        size: imageBlob.size,
      };

      const nextCount = capturedImagesRef.current.length + 1;
      updateCapturedImages((images) => [capturedImage, ...images]);
      setMessage(`Đã chụp ảnh thành công. Tổng cộng ${nextCount} ảnh.`);
    } catch (error) {
      if (controller.signal.aborted) return;

      const errorMessage =
        error instanceof Error ? error.message : "Không thể chụp ảnh";
      setMessage(`Lỗi: ${errorMessage}`);
    } finally {
      if (captureAbortRef.current === controller) {
        captureAbortRef.current = null;
        setIsCapturing(false);
      }
    }
  };

  const downloadImage = (image: CapturedImage) => {
    triggerDownload(image.url, image.fileName);
  };

  const downloadAllImages = async () => {
    if (capturedImages.length === 0) return;

    setIsDownloadingAll(true);
    setMessage("Đang đóng gói ảnh...");

    try {
      const files = await Promise.all(
        [...capturedImages].reverse().map(async (image) => ({
          name: image.fileName,
          data: new Uint8Array(await image.blob.arrayBuffer()),
        })),
      );
      const zipBlob = createZipBlob(files);
      const zipUrl = URL.createObjectURL(zipBlob);
      const timestamp = formatTimestampForFile(new Date());

      triggerDownload(zipUrl, `esp32-cam-captures-${timestamp}.zip`);
      window.setTimeout(() => URL.revokeObjectURL(zipUrl), 1000);
      setMessage(`Đã tải ${capturedImages.length} ảnh trong một file ZIP.`);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Không thể tải toàn bộ ảnh";
      setMessage(`Lỗi: ${errorMessage}`);
    } finally {
      setIsDownloadingAll(false);
    }
  };

  const clearCapturedImages = () => {
    for (const image of capturedImagesRef.current) {
      URL.revokeObjectURL(image.url);
    }

    capturedImagesRef.current = [];
    setCapturedImages([]);
    setMessage("Đã xóa danh sách ảnh đã chụp.");
  };

  const reloadStream = () => {
    setStreamStatus("connecting");
    setStreamKey(Date.now());
    setMessage("Đang kết nối lại luồng camera...");
  };

  return (
    <section className="esp-camera">
      <div className="esp-camera__panel">
        <div className="esp-camera__header">
          <div>
            <p className="esp-camera__eyebrow">ESP32-CAM</p>
            <h2>Luồng trực tiếp</h2>
          </div>

          <span
            className={`esp-camera__live esp-camera__live--${streamStatus}`}
            role="status"
          >
            <span />
            {streamStatusText[streamStatus]}
          </span>
        </div>

        <div className="esp-camera__stream">
          <img
            key={streamKey}
            src={`${streamBaseUrl}/stream?time=${streamKey}`}
            alt="Luồng trực tiếp từ ESP32-CAM"
            onLoad={() => {
              setStreamStatus("live");
              setMessage("");
            }}
            onError={() => {
              setStreamStatus("error");
              setMessage("Không kết nối được luồng ESP32-CAM.");
            }}
          />
        </div>
      </div>

      <aside className="esp-camera__side-panel">
        <div className="esp-camera__side-header">
          <div className="esp-camera__side-icon">
            <i className="fa-solid fa-camera" />
          </div>
          <div>
            <p className="title-sm">Điều khiển camera</p>
            <p className="body-md">Chụp nhiều ảnh và làm mới luồng trực tiếp</p>
          </div>
        </div>

        <div className="esp-camera__actions">
          <button
            type="button"
            className="esp-camera__capture-button"
            onClick={captureImage}
            disabled={isCapturing}
          >
            <i className="fa-solid fa-camera-retro" />
            {isCapturing ? "Đang chụp..." : "Chụp ảnh"}
          </button>

          <button
            type="button"
            className="esp-camera__secondary-button"
            onClick={downloadAllImages}
            disabled={capturedImages.length === 0 || isDownloadingAll}
          >
            <i className="fa-solid fa-file-zipper" />
            {isDownloadingAll ? "Đang đóng gói..." : "Tải tất cả"}
          </button>

          <button
            type="button"
            className="esp-camera__secondary-button"
            onClick={reloadStream}
          >
            <i className="fa-solid fa-rotate-right" />
            Tải lại camera
          </button>
        </div>

        {message ? <p className="esp-camera__message">{message}</p> : null}

        <p className="esp-camera__hint">
          Mỗi lần chụp sẽ được thêm vào danh sách ảnh bên dưới. Nút tải tất cả
          sẽ gom toàn bộ ảnh thành một file ZIP.
        </p>
      </aside>

      {capturedImages.length > 0 ? (
        <div className="esp-camera__result">
          <div className="esp-camera__result-header">
            <div>
              <h3>Ảnh đã chụp</h3>
              <p>{capturedImages.length} ảnh trong phiên hiện tại</p>
            </div>

            <div className="esp-camera__result-actions">
              <button
                type="button"
                onClick={downloadAllImages}
                disabled={isDownloadingAll}
              >
                <i className="fa-solid fa-file-zipper" />
                Tải 1 lượt
              </button>
              <button type="button" onClick={clearCapturedImages}>
                <i className="fa-solid fa-trash-can" />
                Xóa danh sách
              </button>
            </div>
          </div>

          <div className="esp-camera__gallery">
            {capturedImages.map((image, index) => (
              <figure className="esp-camera__thumb" key={image.id}>
                <img
                  src={image.url}
                  alt={`Ảnh chụp ESP32-CAM số ${capturedImages.length - index}`}
                />
                <figcaption>
                  <span>{image.capturedAt}</span>
                  <span>{formatFileSize(image.size)}</span>
                </figcaption>
                <button type="button" onClick={() => downloadImage(image)}>
                  <i className="fa-solid fa-download" />
                  Lưu ảnh này
                </button>
              </figure>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
