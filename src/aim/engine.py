"""Движок наводки: из вектора ошибки (прицел → цель) считает движение мыши за тик.

Чистая математика — без захвата экрана и без мыши, поэтому тестируется на
синтетических целях, без GPU и без обученной модели.

Поведение по ТЗ:
  • Smooth — плавное сближение долями расстояния (для близких целей).
  • Flick  — резкий рывок почти в цель (для дальних), с лёгким overshoot.
  • AUTO   — далеко → flick, близко → smooth, в одном цикле.
  • Скорость неравномерная (jitter) + лёгкая кривизна на флике → «живой» аим.
"""

import math
import random

from .config import AimConfig, AimMode

DEAD_ZONE_PX = 2.0  # ближе этого к цели не дёргаемся (чтобы не дрожать на месте)


class Aimer:
    def __init__(
        self,
        config: AimConfig,
        screen_height: int,
        rng: random.Random | None = None,
    ):
        self.config = config
        self.screen_height = screen_height
        # свой генератор случайностей — чтобы в тестах можно было зафиксировать seed
        self._rng = rng or random.Random()

    def step(self, error_x: float, error_y: float) -> tuple[int, int]:
        """error_x/error_y — вектор от прицела (центра экрана) до точки цели, в пикселях.

        Возвращает (move_x, move_y): на сколько сдвинуть мышь за этот тик.
        """
        cfg = self.config
        distance = math.hypot(error_x, error_y)
        if distance <= DEAD_ZONE_PX:
            return (0, 0)

        if self._is_flick(distance):
            move_x, move_y = self._flick_move(error_x, error_y, distance)
        else:
            move_x, move_y = self._smooth_move(error_x, error_y)

        # калибровка под игровую чувствительность мыши
        move_x *= cfg.sensitivity
        move_y *= cfg.sensitivity
        return (round(move_x), round(move_y))

    def _is_flick(self, distance: float) -> bool:
        cfg = self.config
        if cfg.mode == AimMode.FLICK:
            return True
        if cfg.mode == AimMode.SMOOTH:
            return False
        threshold_px = cfg.flick_threshold_pct / 100.0 * self.screen_height
        return distance > threshold_px

    def _smooth_move(self, error_x: float, error_y: float) -> tuple[float, float]:
        cfg = self.config
        fraction = cfg.speed
        if cfg.jitter > 0:
            fraction *= 1.0 + self._rng.uniform(-cfg.jitter, cfg.jitter)
        fraction = max(0.0, fraction * cfg.intensity)
        return error_x * fraction, error_y * fraction

    def _flick_move(
        self, error_x: float, error_y: float, distance: float
    ) -> tuple[float, float]:
        cfg = self.config
        # ~0.85..1.05 расстояния — быстрый рывок, иногда лёгкий overshoot (>1)
        fraction = self._rng.uniform(0.85, 1.05) * cfg.intensity
        move_x = error_x * fraction
        move_y = error_y * fraction
        # лёгкая кривизна вбок, чтобы траектория не была идеально прямой
        perp_x, perp_y = -error_y / distance, error_x / distance
        curve = self._rng.uniform(-0.05, 0.05) * distance
        return move_x + perp_x * curve, move_y + perp_y * curve
