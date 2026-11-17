"""Captura con OpenCV: reloj monotónico para cámara y tiempo del archivo para video."""

from dataclasses import dataclass
from importlib import import_module
from math import isfinite
from pathlib import Path
import time
from typing import Any, Callable, Optional


class CaptureError(RuntimeError):
    """No se pudo abrir la fuente, leer una imagen u obtener su tiempo."""


@dataclass(frozen=True)
class CapturedFrame:
    image: Any
    timestamp: float
    index: int


class OpenCVSource:
    """Lee una cámara o un archivo de video. read() devuelve None solo al terminar el video."""

    def __init__(self, source=0, *, video_fps: Optional[float] = None,
                 cv2_module=None, clock: Callable[[], float] = time.monotonic):
        if isinstance(source, bool) or (isinstance(source, int) and source < 0):
            raise ValueError("El indice de camara debe ser un entero no negativo")
        if video_fps is not None and (not isfinite(video_fps) or video_fps <= 0):
            raise ValueError("video_fps debe ser finito y positivo")
        self.is_video = not isinstance(source, int)
        if video_fps is not None and not self.is_video:
            raise ValueError("video_fps solamente se aplica a archivos de video")
        self.source = str(source) if self.is_video else source
        self._cv = cv2_module
        self._clock = clock
        self._override_fps = video_fps
        self._cap = None
        self._index = 0
        self._last_timestamp = None
        self._media_origin = None
        self._fallback = False
        self.fps = None
        self.frame_count = 0
        self.timing_warning = None

    def __enter__(self):
        if self.is_video and not Path(self.source).is_file():
            raise CaptureError(f"No existe el archivo de video: {self.source}")
        self._cv = self._cv or import_module("cv2")
        try:
            self._cap = self._cv.VideoCapture(self.source)
            if not self._cap.isOpened():
                raise CaptureError(f"No se pudo abrir la fuente: {self.source}")
            fps = self._override_fps or self._cap.get(self._cv.CAP_PROP_FPS)
            self.fps = fps if isfinite(fps) and fps > 0 else None
            count = self._cap.get(self._cv.CAP_PROP_FRAME_COUNT)
            self.frame_count = int(count) if isfinite(count) and count > 0 else 0
            return self
        except Exception:
            self.close()
            raise

    def read(self) -> Optional[CapturedFrame]:
        if self._cap is None:
            raise CaptureError("La fuente no esta abierta")
        try:
            ok, image = self._cap.read()
            if not ok or image is None or getattr(image, "size", 0) == 0:
                if not self.is_video:
                    raise CaptureError("Se perdio la camara o no se pudo leer una imagen")
                if self._index == 0:
                    raise CaptureError("El video esta vacio o no se pudo decodificar")
                if self.frame_count and self._index < self.frame_count - 1:
                    raise CaptureError("La lectura fallo antes del final informado del video")
                return None
            timestamp = self._video_time() if self.is_video else self._clock()
            if (not isfinite(timestamp) or timestamp < 0 or
                    (self._last_timestamp is not None and timestamp <= self._last_timestamp)):
                raise CaptureError("La fuente no produjo tiempos válidos y siempre crecientes")
            result = CapturedFrame(image, timestamp, self._index)
            self._last_timestamp = timestamp
            self._index += 1
            return result
        except CaptureError:
            raise
        except Exception as exc:
            raise CaptureError(f"Error leyendo {self.source}: {exc}") from exc

    def _video_time(self) -> float:
        if self._override_fps is not None:
            return self._index / self._override_fps
        position = self._cap.get(self._cv.CAP_PROP_POS_MSEC) / 1000.0
        if not self._fallback and isfinite(position) and position >= 0:
            if self._media_origin is None:
                self._media_origin = position
            timestamp = position - self._media_origin
            if self._last_timestamp is None or timestamp > self._last_timestamp:
                return timestamp
        if self.fps is None:
            raise CaptureError("Video sin tiempos utilizables; indica --video-fps con su FPS real")
        # Si falla el tiempo del video, seguimos con FPS para no mezclar relojes.
        self._fallback = True
        self.timing_warning = "Tiempos de video no disponibles: aproximando con FPS constantes"
        return 0.0 if self._last_timestamp is None else self._last_timestamp + 1 / self.fps

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __exit__(self, exc_type, exc, traceback):
        self.close()
