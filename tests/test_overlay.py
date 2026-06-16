"""Тесты сборки состояния оверлея (без GUI).
Запуск из корня:  python -m unittest discover -s tests -t .
"""

import unittest

from src.aim import AimConfig, AimTarget
from src.aim.overlay import build_overlay_state
from src.domain import Box, Enemy, EnemyHead, Teammate

W, H = 1000, 1000


class OverlayStateTests(unittest.TestCase):
    def test_collects_boxes_target_and_zone(self):
        cfg = AimConfig(target=AimTarget.BODY, area_width_pct=40, area_height_pct=50)
        enemy = Enemy(
            body=Box(10, 20, 50, 120),
            head=EnemyHead(Box(20, 25, 40, 45), confidence=0.9),
            confidence=0.9,
        )
        mate = Teammate(body=Box(200, 50, 240, 150), confidence=0.8)

        state = build_overlay_state(
            [enemy], [mate], enemy, (30.0, 70.0), cfg, W, H, (5, 7), 123.0
        )

        self.assertEqual(state.region, (5, 7, W, H))
        self.assertEqual(state.enemies, [(10, 20, 50, 120)])
        self.assertEqual(state.heads, [(20, 25, 40, 45)])
        self.assertEqual(state.teammates, [(200, 50, 240, 150)])
        self.assertEqual(state.target_box, (10, 20, 50, 120))
        self.assertEqual(state.aim_point, (30.0, 70.0))  # сглаженная точка от трекера
        self.assertEqual(state.zone, (300.0, 250.0, 700.0, 750.0))
        self.assertEqual(state.timestamp, 123.0)

    def test_without_target_and_heads(self):
        cfg = AimConfig(target=AimTarget.BODY)
        enemy = Enemy(body=Box(0, 0, 10, 10), confidence=0.5)  # головы нет

        state = build_overlay_state([enemy], [], None, None, cfg, W, H, (0, 0), 1.0)

        self.assertEqual(state.enemies, [(0, 0, 10, 10)])
        self.assertEqual(state.heads, [])
        self.assertEqual(state.teammates, [])
        self.assertIsNone(state.target_box)
        self.assertIsNone(state.aim_point)


if __name__ == "__main__":
    unittest.main()
