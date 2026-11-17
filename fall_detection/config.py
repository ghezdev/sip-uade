"""Umbrales iniciales, pendientes de validación con videos grabados."""

from dataclasses import dataclass, fields
from math import isfinite


@dataclass(frozen=True)
class DetectorConfig:
    fall_speed_threshold: float = 1.2  # longitudes del torso de referencia por segundo
    min_descent: float = 0.5  # longitudes del torso de referencia
    lying_aspect_ratio: float = 1.0
    upright_aspect_ratio: float = 0.65
    min_visibility: float = 0.5
    speed_window_seconds: float = 0.5
    fall_timeout_seconds: float = 1.5
    floor_confirm_seconds: float = 15.0
    recovery_seconds: float = 5.0  # al confirmar la recuperación se habilita un nuevo episodio
    tracking_timeout_seconds: float = 1.0
    max_sample_gap_seconds: float = 0.5
    recovery_hip_tolerance: float = 0.25  # descenso permitido respecto de la cadera previa, en torsos
    posture_window_seconds: float = 4.0
    posture_hold_seconds: float = 0.75
    posture_min_descent: float = 0.25
    posture_angle_change: float = 30.0
    posture_rotation_threshold: float = 45.0
    posture_aspect_change: float = 0.4
    lying_torso_angle: float = 60.0
    upright_torso_angle: float = 30.0
    floor_persistence_seconds: float = 5.0

    def __post_init__(self) -> None:
        # Todos los parámetros deben ser números finitos y positivos.
        for field in fields(self):
            value = getattr(self, field.name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{field.name} debe ser un número finito y positivo")
        if self.min_visibility > 1:
            raise ValueError("min_visibility debe ser <= 1")
        if self.upright_aspect_ratio >= self.lying_aspect_ratio:
            raise ValueError("upright_aspect_ratio debe ser < lying_aspect_ratio")
        if self.max_sample_gap_seconds > self.tracking_timeout_seconds:
            raise ValueError("max_sample_gap_seconds debe ser <= tracking_timeout_seconds")
        if not self.upright_torso_angle < self.lying_torso_angle <= 90:
            raise ValueError("Los ángulos deben cumplir 0 < upright_torso_angle < lying_torso_angle <= 90")
        if not self.posture_angle_change <= self.posture_rotation_threshold <= 90:
            raise ValueError("Los ángulos deben cumplir posture_angle_change <= posture_rotation_threshold <= 90")
        if self.posture_window_seconds < self.speed_window_seconds:
            raise ValueError("posture_window_seconds debe ser >= speed_window_seconds")
        if self.posture_hold_seconds > self.floor_persistence_seconds:
            raise ValueError("posture_hold_seconds debe ser <= floor_persistence_seconds")
