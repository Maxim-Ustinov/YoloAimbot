"""Тесты движка наводки (Aimer).
Запуск из корня C:\\AI:  python -m unittest discover -s tests -t .
"""

import math
import random
import unittest

from src.aim import AimConfig, AimMode
from src.aim.engine import Aimer

SCREEN_H = 1440


def make_aimer(seed: int = 0, **overrides) -> Aimer:
    cfg = AimConfig(**overrides)
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

    def test_sensitivity_scales_output(self):
        err = (120.0, 40.0)
        base = make_aimer(seed=2, sensitivity=1.0, mode=AimMode.SMOOTH).step(*err)
        scaled = make_aimer(seed=2, sensitivity=2.0, mode=AimMode.SMOOTH).step(*err)
        # одинаковый seed → та же случайность → ровно в 2 раза больше (± округление)
        self.assertAlmostEqual(scaled[0], base[0] * 2, delta=1)
        self.assertAlmostEqual(scaled[1], base[1] * 2, delta=1)


if __name__ == "__main__":
    unittest.main()
