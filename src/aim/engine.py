"""Движок наводки: из вектора ошибки (прицел → цель) считает движение мыши за тик.

Чистая математика — без захвата экрана и без мыши, поэтому тестируется на
синтетических целях, без GPU и без обученной модели.

Поведение по ТЗ:
  • Smooth — плавное сближение долями расстояния (для близких целей).
  • Flick  — резкий рывок почти в цель (для дальних), с лёгким overshoot.
  • AUTO   — далеко → flick, близко → smooth, в одном цикле.
  • jitter — низкочастотный дрейф прицела (не покадровая дрожь) + лёгкая
    кривизна на флике → «живой» аим.

Здесь же решение триггербота should_fire(): чистая функция, тестируется
без мыши и без модели.
"""

import math
import random

from .config import AimConfig, AimMode

DEAD_ZONE_PX = 2.0  # ближе этого к цели не дёргаемся (чтобы не дрожать на месте)
MAX_UI_SPEED = 5000.0
MAX_UI_FORCE = 100.0


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
        # текущее смещение плавного случайного дрейфа (см. _advance_noise)
        self._noise_x = 0.0
        self._noise_y = 0.0

    def step(self, error_x: float, error_y: float) -> tuple[int, int]:
        """error_x/error_y — вектор от прицела (центра экрана) до точки цели, в пикселях.

        Возвращает (move_x, move_y): на сколько сдвинуть мышь за этот тик.
        """
        cfg = self.config
        distance = math.hypot(error_x, error_y)
        if distance <= DEAD_ZONE_PX:
            return (0, 0)

        if self._is_flick(distance):
            move_x, move_y = self._flick_move(error_x, error_y)
        else:
            move_x, move_y = self._smooth_move(error_x, error_y)

        # Анти-перелёт: шаг не длиннее, чем до цели — прицел садится в цель,
        # а не проскакивает (главная причина «облёта» головы при наводке).
        move_len = math.hypot(move_x, move_y)
        if move_len > distance:
            scale = distance / move_len
            move_x *= scale
            move_y *= scale

        # Screenshot-style sensitivity: it divides mouse coordinates.
        sensitivity = max(0.1, float(cfg.sensitivity))
        move_x /= sensitivity
        move_y /= sensitivity

        random_range = max(0.0, float(getattr(cfg, "jitter", 0.0)))
        if random_range > 0:
            # плавный дрейф вместо независимого шума на каждый тик:
            # покадровый шум выглядит как дрожь робота, дрейф — как живая рука
            self._noise_x = self._advance_noise(self._noise_x, random_range)
            self._noise_y = self._advance_noise(self._noise_y, random_range)
            move_x += self._noise_x
            move_y += self._noise_y

        max_step = getattr(cfg, "max_step_px", 0.0)
        if max_step > 0:
            length = math.hypot(move_x, move_y)
            if length > max_step:
                scale = max_step / length
                move_x *= scale
                move_y *= scale
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
        # Адаптивная жёсткость: у цели сила наведения растёт к максимуму, чтобы
        # прицел уверенно «садился» в голову, а не вяло подползал. Вдали — базовая
        # Aim Force. near_px — радиус, внутри которого включается полный дожим.
        distance = math.hypot(error_x, error_y)
        near_px = max(10.0, 0.06 * self.screen_height)
        close = max(0.0, min(1.0, 1.0 - distance / near_px))
        force = self._force_fraction()
        eff_force = force + (1.0 - force) * close
        fraction = self._speed_fraction() * eff_force
        return error_x * fraction, error_y * fraction

    def _flick_move(self, error_x: float, error_y: float) -> tuple[float, float]:
        # быстрый рывок к цели; лёгкий разброс магнитуды для «живого» движения.
        # Без перпендикулярной кривизны: в auto-режиме флик может срабатывать
        # каждый кадр, и боковая случайность копилась бы в колебания влево-вправо.
        fraction = self._rng.uniform(0.85, 1.05) * self._force_fraction()
        return error_x * fraction, error_y * fraction

    def _advance_noise(self, value: float, amplitude: float) -> float:
        # маленький случайный шаг + затухание к нулю, в пределах ±amplitude
        value = value * 0.9 + self._rng.uniform(-0.2, 0.2) * amplitude
        return max(-amplitude, min(amplitude, value))

    def _speed_fraction(self) -> float:
        return max(0.0, min(1.0, float(self.config.speed) / MAX_UI_SPEED))

    def _force_fraction(self) -> float:
        return max(0.0, min(1.0, float(self.config.intensity) / MAX_UI_FORCE))


def should_fire(distance: float, now: float, last_shot: float, config: AimConfig) -> bool:
    """Решение триггербота: точка прицеливания достаточно близко и кулдаун прошёл.

    distance — расстояние от прицела до точки прицеливания, px;
    now/last_shot — time.monotonic() текущего момента и предыдущего выстрела.
    """
    if not getattr(config, "trigger_enabled", False):
        return False
    if distance > max(0.0, float(config.trigger_radius_px)):
        return False
    return now - last_shot >= max(0.0, float(config.trigger_interval_ms)) / 1000.0
