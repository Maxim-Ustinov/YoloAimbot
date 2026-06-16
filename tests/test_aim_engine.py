"""Тесты движка наводки (Aimer).
Запуск из корня C:\\AI:  python -m unittest discover -s tests -t .
"""

import math
import random
import unittest

from src.aim import AimConfig, AimMode
from src.aim.engine import Aimer, should_fire

SCREEN_H = 1440


def make_aimer(seed: int = 0, **overrides) -> Aimer:
    defaults = {"sensitivity": 1.0, "jitter": 0.0}
    defaults.update(overrides)
    cfg = AimConfig(**defaults)
    return Aimer(cfg, screen_height=SCREEN_H, rng=random.Random(seed))


class AimerTests(unittest.TestCase):
    def test_dead_zone_no_move(self):
        aimer = make_aimer()
        self.assertEqual(aimer.step(0, 0), (0, 0))
        self.assertEqual(aimer.step(1, 0), (0, 0))  # внутри мёртвой зоны

    def test_moves_toward_target(self):
        aimer = make_aimer(mode=AimMode.SMOOTH)
        mx, my = aimer.step(100, 60)
        self.assertGreater(mx, 0)
        self.assertGreater(my, 0)
        # шаг короче, чем всё расстояние (плавно, не телепорт)
        self.assertLess(math.hypot(mx, my), math.hypot(100, 60))

    def test_smooth_reduces_distance(self):
        aimer = make_aimer(mode=AimMode.SMOOTH)
        ex, ey = 200.0, 0.0
        mx, my = aimer.step(ex, ey)
        self.assertLess(math.hypot(ex - mx, ey - my), 200.0)

    def test_flick_faster_than_smooth(self):
        err = (300.0, 0.0)
        flick = make_aimer(seed=1, mode=AimMode.FLICK).step(*err)
        smooth = make_aimer(seed=1, mode=AimMode.SMOOTH).step(*err)
        self.assertGreater(abs(flick[0]), abs(smooth[0]))

    def test_auto_flicks_when_far(self):
        # порог = 15% * 1440 = 216 px; цель на 500 px → флик (большой шаг)
        aimer = make_aimer(mode=AimMode.AUTO)
        far = aimer.step(500, 0)
        self.assertGreater(abs(far[0]), 250)

    def test_auto_smooth_when_near(self):
        # 100 px < 216 px → smooth (маленький шаг)
        aimer = make_aimer(mode=AimMode.AUTO)
        near = aimer.step(100, 0)
        self.assertLess(abs(near[0]), 60)

    def test_sensitivity_divides_output(self):
        err = (120.0, 40.0)
        base = make_aimer(seed=2, sensitivity=1.0, mode=AimMode.SMOOTH).step(*err)
        divided = make_aimer(seed=2, sensitivity=2.0, mode=AimMode.SMOOTH).step(*err)
        self.assertAlmostEqual(divided[0], base[0] / 2, delta=1)
        self.assertAlmostEqual(divided[1], base[1] / 2, delta=1)

    def test_speed_uses_ui_scale(self):
        err = (100.0, 0.0)
        slow = make_aimer(mode=AimMode.SMOOTH, speed=2500, intensity=100).step(*err)
        fast = make_aimer(mode=AimMode.SMOOTH, speed=5000, intensity=100).step(*err)
        self.assertAlmostEqual(slow[0], 50, delta=1)
        self.assertAlmostEqual(fast[0], 100, delta=1)

    def test_max_step_clamps_output(self):
        mover = make_aimer(mode=AimMode.FLICK, max_step_px=25, sensitivity=1.0)
        mx, my = mover.step(500, 0)
        self.assertLessEqual(math.hypot(mx, my), 25.5)

    def test_jitter_is_smooth_drift(self):
        # дрейф ограничен амплитудой и не прыгает между тиками (не покадровый шум)
        clean = make_aimer(mode=AimMode.SMOOTH).step(100, 50)  # без jitter — детерминирован
        noisy = make_aimer(seed=3, mode=AimMode.SMOOTH, jitter=10)
        prev = None
        for _ in range(20):
            mx, my = noisy.step(100, 50)
            offset = (mx - clean[0], my - clean[1])
            self.assertLessEqual(abs(offset[0]), 11)  # амплитуда 10 + округление
            self.assertLessEqual(abs(offset[1]), 11)
            if prev is not None:
                self.assertLessEqual(abs(offset[0] - prev[0]), 4)  # плавно
                self.assertLessEqual(abs(offset[1] - prev[1]), 4)
            prev = offset


class TriggerTests(unittest.TestCase):
    def _cfg(self, **overrides) -> AimConfig:
        defaults = {
            "trigger_enabled": True,
            "trigger_radius_px": 8.0,
            "trigger_interval_ms": 150.0,
        }
        defaults.update(overrides)
        return AimConfig(**defaults)

    def test_disabled_never_fires(self):
        cfg = self._cfg(trigger_enabled=False)
        self.assertFalse(should_fire(0.0, 10.0, 0.0, cfg))

    def test_fires_when_close_and_cooldown_passed(self):
        self.assertTrue(should_fire(5.0, 10.0, 9.8, self._cfg()))  # прошло 200 мс

    def test_does_not_fire_when_far(self):
        self.assertFalse(should_fire(9.0, 10.0, 0.0, self._cfg()))  # 9 px > радиуса 8

    def test_respects_cooldown(self):
        self.assertFalse(should_fire(5.0, 10.0, 9.9, self._cfg()))  # 100 мс < 150 мс


if __name__ == "__main__":
    unittest.main()
