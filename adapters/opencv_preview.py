"""Vista opcional de diagnóstico, sin intervenir en la detección."""

from importlib import import_module
from math import isfinite
import time

from fall_detection import EventType


# Conexiones entre los 33 puntos de MediaPipe, usadas solo para dibujar.
POSE_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 7), (0, 4), (4, 5), (5, 6), (6, 8), (9, 10),
    (11, 12), (11, 13), (13, 15), (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16), (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24), (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32),
)


def diagnostic_lines(result, diagnostic=None, *, elapsed_seconds=None):
    def number(value):
        return "--" if value is None else f"{value:.2f}"
    m = result.metrics
    display_time = result.timestamp if elapsed_seconds is None else elapsed_seconds
    return [
        f"Estado: {result.state.value} | Seguimiento: {result.tracking.value}",
        f"t={display_time:.2f}s  aspecto={number(m.aspect_ratio)}  "
        f"descenso={number(m.hip_descent)}  velocidad={number(m.fall_speed)}",
        f"Criterio: {result.criterion.value if result.criterion else '--'} | "
        f"Torso: {number(m.torso_angle)} grados | Descenso corporal: {number(m.body_descent)}",
        f"Candidato horizontal: {m.candidate_seconds:.1f}s | Giro: {number(m.posture_change)} grados",
        f"Permanencia acumulada: {m.floor_seconds:.1f}s | Recuperacion estable: {m.recovery_seconds:.1f}s",
        diagnostic or m.invalid_reason or "Medicion valida",
        "q / Esc: salir | ON_FLOOR: postura compatible; ubicacion no confirmada",
    ]


class FallingIndicator:
    """Mantiene visible FALLING sin cambiar el tiempo ni el estado del detector."""

    def __init__(self, hold_seconds=2.0):
        self.hold_seconds = hold_seconds
        self._until = float('-inf')
        self._event = None

    def observe(self, result, display_time):
        for event in result.events:
            if event.type == EventType.FALL_STARTED and event.event_id != self._event:
                self._until = display_time + self.hold_seconds
                self._event = event.event_id
        return "Evento reciente: FALLING (fall_started)" if display_time < self._until else None


class OpenCVPreview:
    def __init__(self, min_visibility, *, cv2_module=None):
        self._cv = cv2_module or import_module("cv2")
        self.min_visibility = min_visibility
        self.title = "Detector de caidas - diagnostico"
        self._falling_indicator = FallingIndicator()
        self._time_origin = None

    def __enter__(self):
        self._cv.namedWindow(self.title, self._cv.WINDOW_NORMAL)
        return self

    def show(self, frame, observation, result, *, delay_ms=1, notice=None, alert=None,
             notification=None):
        image = frame.copy()
        height, width = image.shape[:2]
        points = {}
        for i, p in enumerate(observation.landmarks):
            if (all(isinstance(v, (int, float)) and isfinite(v)
                    for v in (p.x, p.y, p.visibility))
                    and p.visibility >= self.min_visibility and 0 <= p.x <= 1 and 0 <= p.y <= 1):
                points[i] = (int(p.x * (width - 1)), int(p.y * (height - 1)))
        for a, b in POSE_CONNECTIONS:
            if a in points and b in points:
                self._cv.line(image, points[a], points[b], (0, 210, 255), 2)
        for point in points.values():
            self._cv.circle(image, point, 3, (80, 240, 80), -1)
        # El panel va debajo de la imagen para no tapar a la persona.
        if self._time_origin is None:
            self._time_origin = result.timestamp
        # Solo el tiempo mostrado es relativo; el detector conserva sus timestamps.
        lines = diagnostic_lines(result, observation.diagnostic,
                                 elapsed_seconds=result.timestamp - self._time_origin)
        falling_notice = self._falling_indicator.observe(result, time.monotonic())
        if falling_notice:
            lines.insert(-1, falling_notice)
        if alert is not None:
            remaining = ("" if alert.remaining_seconds is None
                         else f" ({alert.remaining_seconds:.1f}s restantes)")
            text = ("Alerta pausada por recuperacion" if alert.paused
                    else f"Alerta local: {alert.state.value}")
            if notification is not None:
                text = notification
            lines.insert(-1, f"{text}{remaining}")
        if notice:
            lines.insert(-1, notice)
        image = self._cv.copyMakeBorder(image, 0, 30 * len(lines), 0, max(0, 960 - width),
                                        self._cv.BORDER_CONSTANT, value=(25, 25, 25))
        for i, text in enumerate(lines):
            self._cv.putText(image, text, (12, height + 24 + i * 26),
                             self._cv.FONT_HERSHEY_SIMPLEX, 0.52, (235, 235, 235), 1)
        self._cv.imshow(self.title, image)
        key = self._cv.waitKey(max(1, min(delay_ms, 1000))) & 0xFF
        if key in (ord("q"), 27):
            return False
        try:
            return self._cv.getWindowProperty(self.title, self._cv.WND_PROP_VISIBLE) >= 1
        except self._cv.error:
            # OpenCV puede lanzar un error si la ventana ya se cerró.
            return False

    def __exit__(self, exc_type, exc, traceback):
        self._cv.destroyAllWindows()
