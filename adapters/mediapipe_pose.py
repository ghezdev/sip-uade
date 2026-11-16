"""Convierte las posturas de MediaPipe Tasks en mediciones para el motor."""

from dataclasses import dataclass
from importlib import import_module
from math import atan2, degrees, hypot, isfinite
from pathlib import Path
from typing import Optional, Sequence

from fall_detection import Measurement


class PoseError(RuntimeError):
    """Falló el procesamiento de postura; no significa que la persona esté ausente."""


@dataclass(frozen=True)
class Landmark:
    x: float
    y: float
    visibility: float


@dataclass(frozen=True)
class PoseObservation:
    measurement: Measurement
    landmarks: tuple[Landmark, ...] = ()
    diagnostic: Optional[str] = None


def landmarks_to_measurement(
    landmarks: Sequence[Landmark], timestamp: float, width: int, height: int,
    min_visibility: float,
) -> PoseObservation:
    """Usa el alto de la imagen como unidad: x'=x*width/height, y'=y.

    Exige hombros, caderas y al menos ocho puntos visibles dentro de la imagen.
    Si un hombro o una cadera queda afuera, la medición se marca como inválida.
    """
    points = tuple(landmarks)
    if not points:
        return PoseObservation(Measurement(timestamp, False), diagnostic="Sin persona detectada")

    def invalid(reason):
        return PoseObservation(Measurement(timestamp, True), points, reason)

    if width <= 0 or height <= 0 or len(points) != 33:
        return invalid("Dimensiones o cantidad de puntos corporales invalidas")

    def usable(p):
        return (all(isinstance(v, (int, float)) and isfinite(v)
                    for v in (p.x, p.y, p.visibility))
                and 0 <= p.x <= 1 and 0 <= p.y <= 1 and 0 <= p.visibility <= 1)

    key = [points[i] for i in (11, 12, 23, 24)]
    if not all(usable(p) for p in key):
        return invalid("Hombros/caderas fuera de imagen o con valores invalidos")
    visibility = min(p.visibility for p in key)
    # Conservamos la visibilidad medida para que el motor informe low_visibility.
    if visibility < min_visibility:
        return PoseObservation(Measurement(timestamp, True, visibility=visibility), points,
                               "Baja visibilidad en hombros/caderas")
    visible = [p for p in points if usable(p) and p.visibility >= min_visibility]
    if len(visible) < 8:
        return invalid("Menos de ocho puntos visibles en la imagen")
    scale = width / height
    left_shoulder, right_shoulder, left_hip, right_hip = key
    shoulder_x = (left_shoulder.x + right_shoulder.x) * scale / 2
    shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
    hip_x = (left_hip.x + right_hip.x) * scale / 2
    hip_y = (left_hip.y + right_hip.y) / 2
    torso = hypot(shoulder_x - hip_x, shoulder_y - hip_y)
    body_height = max(p.y for p in visible) - min(p.y for p in visible)
    body_width = (max(p.x for p in visible) - min(p.x for p in visible)) * scale
    if torso <= 0 or body_height <= 0 or body_width <= 0:
        return invalid("Geometria corporal degenerada")
    return PoseObservation(Measurement(
        timestamp=timestamp, person_present=True, hip_y=hip_y,
        torso_length=torso, aspect_ratio=body_width / body_height,
        visibility=visibility, shoulder_y=shoulder_y,
        torso_angle=degrees(atan2(abs(shoulder_x - hip_x), abs(shoulder_y - hip_y))),
    ), points)


class MediaPipePose:
    """Reutiliza una tarea en modo VIDEO para cámara y archivos de video.

    Cada imagen se procesa antes de leer la siguiente, sin descartar resultados.
    Solo MediaPipe recibe milisegundos; el motor conserva los segundos originales.
    """

    def __init__(self, model_path, *, min_visibility: float, mp_module=None, cv2_module=None):
        self.model_path = Path(model_path)
        self.min_visibility = min_visibility
        self._mp = mp_module
        self._cv = cv2_module
        self._task = None
        self._last_ms = -1
        self._last_timestamp = None

    def __enter__(self):
        if not self.model_path.is_file():
            raise PoseError("Falta el modelo .task. Ejecuta: python runner.py --download-model")
        self._mp = self._mp or import_module("mediapipe")
        self._cv = self._cv or import_module("cv2")
        try:
            vision = self._mp.tasks.vision
            options = vision.PoseLandmarkerOptions(
                base_options=self._mp.tasks.BaseOptions(model_asset_path=str(self.model_path.resolve())),
                running_mode=vision.RunningMode.VIDEO, num_poses=1,
                min_pose_detection_confidence=0.5, min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._task = vision.PoseLandmarker.create_from_options(options)
            return self
        except Exception as exc:
            raise PoseError(f"No se pudo cargar el modelo de pose: {exc}") from exc

    def process(self, frame, timestamp: float) -> PoseObservation:
        if self._task is None:
            raise PoseError("El adaptador de pose no esta abierto")
        if (not isfinite(timestamp) or timestamp < 0 or
                (self._last_timestamp is not None and timestamp <= self._last_timestamp)):
            raise PoseError("La postura requiere tiempos válidos y siempre crecientes, en segundos")
        try:
            rgb = self._cv.cvtColor(frame, self._cv.COLOR_BGR2RGB)
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
            millis = max(int(timestamp * 1000), self._last_ms + 1)
            result = self._task.detect_for_video(image, millis)
            self._last_ms = millis
            self._last_timestamp = timestamp
            points = tuple(Landmark(p.x, p.y, p.visibility) for p in result.pose_landmarks[0]) \
                if result.pose_landmarks else ()
            height, width = frame.shape[:2]
            return landmarks_to_measurement(points, timestamp, width, height, self.min_visibility)
        except Exception as exc:
            raise PoseError(f"Fallo la inferencia de pose: {exc}") from exc

    def close(self) -> None:
        if self._task is not None:
            self._task.close()
            self._task = None

    def __exit__(self, exc_type, exc, traceback):
        self.close()
