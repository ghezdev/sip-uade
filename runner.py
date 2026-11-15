"""Local composition root: capture -> pose measurements -> detector -> diagnostics."""

import argparse
from dataclasses import replace
from contextlib import ExitStack
import logging
from math import isfinite
from pathlib import Path
import sys
import time
from urllib.request import urlopen

from adapters.camera import CaptureError, OpenCVSource
from adapters.mediapipe_pose import MediaPipePose, PoseError
from adapters.opencv_preview import OpenCVPreview
from fall_detection import DetectorConfig, FallDetector
from alerts import AlertWorkflow


DEFAULT_MODEL = Path(__file__).resolve().parent / "models" / "pose_landmarker_lite.task"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_lite/float16/1/pose_landmarker_lite.task")
LOG = logging.getLogger("fall_detector")


def crop_frame(image, mode="none"):
    """Select native pixels without resizing; right owns the odd center column."""
    if mode == "none":
        return image
    if mode not in ("left", "right"):
        raise ValueError("--crop debe ser left, right o none")
    if len(image.shape) < 2 or image.shape[0] < 1 or image.shape[1] < 2:
        raise ValueError("El recorte requiere una imagen con alto positivo y ancho minimo de 2 pixeles")
    middle = image.shape[1] // 2
    # Copy to keep an independent, contiguous image for MediaPipe/OpenCV.
    return (image[:, :middle] if mode == "left" else image[:, middle:]).copy()


def download_model(path: Path) -> None:
    """Explicit download, no network during normal detection. Atomic local write."""
    import os
    import tempfile
    import zipfile

    if path.exists():
        raise ValueError(f"El modelo ya existe: {path}. No se sobrescribio.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as out:
            temporary = Path(out.name)
            with urlopen(MODEL_URL, timeout=30) as response:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
        if not zipfile.is_zipfile(temporary):
            raise ValueError("La descarga no contiene un modelo Tasks valido")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def parser():
    p = argparse.ArgumentParser(description="Detector local de caidas: webcam o archivo de video")
    source = p.add_mutually_exclusive_group()
    source.add_argument("--camera", type=int, default=None, help="Indice de webcam (por defecto: 0)")
    source.add_argument("--video", type=Path, help="Ruta de un archivo de video")
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Ruta del modelo Pose Landmarker .task")
    p.add_argument("--download-model", action="store_true", help="Descarga el modelo oficial y termina")
    p.add_argument("--video-fps", type=float, help="FPS reales para reemplazar tiempos de video defectuosos")
    p.add_argument("--no-preview", action="store_true", help="Procesa sin ventana, con eventos en consola")
    p.add_argument("--crop", choices=("left", "right", "none"), default="none",
                   help="Procesa la mitad izquierda, derecha o la imagen completa (por defecto: none)")
    p.add_argument("--recovery-seconds", type=float, default=5.0,
                   help="Segundos de recuperacion estable para cerrar y rearmar (por defecto: 5)")
    p.add_argument("--cancel-seconds", type=float, default=30.0,
                   help="Ventana local tras confirmar caida; no envia mensajes (por defecto: 30)")
    p.add_argument("--floor-confirm-seconds", type=float, default=15.0,
                   help="Permanencia acumulada para confirmar (por defecto: 15; reducir solo para pruebas)")
    return p


def run(args) -> int:
    if args.download_model:
        download_model(args.model)
        LOG.info("Modelo descargado: %s", args.model)
        return 0
    detector = FallDetector(replace(DetectorConfig(), recovery_seconds=args.recovery_seconds,
                                   floor_confirm_seconds=args.floor_confirm_seconds))
    alerts = AlertWorkflow(args.cancel_seconds)
    with ExitStack() as stack:
        # Load model before opening camera; a missing model must not lock the device.
        pose = stack.enter_context(MediaPipePose(args.model, min_visibility=detector.config.min_visibility))
        source = stack.enter_context(OpenCVSource(
            args.video if args.video is not None else (args.camera if args.camera is not None else 0),
            video_fps=args.video_fps,
        ))
        preview = None if args.no_preview else stack.enter_context(
            OpenCVPreview(detector.config.min_visibility))
        warned = None
        last_health = None
        last_alert = None
        last_state = None
        frame_count = 0
        started = time.monotonic()
        while True:
            began = time.monotonic()
            frame = source.read()
            if frame is None:
                LOG.info("Fin del video: %d cuadros procesados", frame_count)
                return 0
            image = crop_frame(frame.image, args.crop)
            observation = pose.process(image, frame.timestamp)
            result = detector.update(observation.measurement)
            alert = alerts.update(result.events, frame.timestamp)
            if (alert.state, alert.episode_id) != last_alert:
                LOG.info("alerta_local=%s episodio=%s vencimiento=%s", alert.state.value,
                         alert.episode_id, alert.deadline)
                last_alert = (alert.state, alert.episode_id)
            if result.state != last_state:
                LOG.info("estado=%s t=%.3f acumulado=%.2fs criterio=%s", result.state.value,
                         frame.timestamp, result.metrics.floor_seconds,
                         result.criterion.value if result.criterion else "--")
                last_state = result.state
            for event in result.events:
                LOG.info("evento=%s t=%.3f episodio=%s criterio=%s", event.type.value,
                         event.timestamp, event.episode_id,
                         event.criterion.value if event.criterion else "--")
            health = (result.tracking, observation.diagnostic, result.metrics.invalid_reason)
            if health != last_health:
                LOG.info("seguimiento=%s detalle=%s", result.tracking.value,
                         observation.diagnostic or result.metrics.invalid_reason or "Medicion valida")
                last_health = health
            if source.timing_warning and warned != source.timing_warning:
                LOG.warning(source.timing_warning)
                warned = source.timing_warning
            frame_count += 1
            if preview:
                delay = 1
                if source.is_video and source.fps:
                    delay = max(1, int((1 / source.fps - (time.monotonic() - began)) * 1000))
                if not preview.show(image, observation, result, delay_ms=delay,
                                    notice=source.timing_warning, alert=alert):
                    LOG.info("Cierre solicitado; %d cuadros procesados", frame_count)
                    return 0
            if frame_count % 300 == 0:
                LOG.info("cuadros=%d rendimiento=%.1f FPS", frame_count,
                         frame_count / max(time.monotonic() - started, 0.001))


def main(argv=None) -> int:
    p = parser()
    args = p.parse_args(argv)
    if args.camera is not None and args.camera < 0:
        p.error("--camera debe ser no negativo")
    if args.video_fps is not None and (args.video is None or not isfinite(args.video_fps) or args.video_fps <= 0):
        p.error("--video-fps requiere --video y un numero finito positivo")
    for name in ("recovery_seconds", "cancel_seconds", "floor_confirm_seconds"):
        value = getattr(args, name)
        if not isfinite(value) or value <= 0:
            p.error(f"--{name.replace('_', '-')} debe ser finito y positivo")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        return run(args)
    except KeyboardInterrupt:
        LOG.info("Interrumpido por el usuario")
        return 0
    except ImportError as exc:
        LOG.error("Falta una dependencia (%s). Ejecuta: python -m pip install -r requirements.txt", exc)
        return 1
    except (CaptureError, PoseError, OSError, ValueError) as exc:
        LOG.error("%s", exc)
        return 1
    except Exception as exc:
        LOG.error("Fallo del runtime o de la ventana OpenCV: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
