"""Тесты выбора цели (targeting).
Запуск из корня:  python -m unittest discover -s tests -t .
"""

import unittest

from src.aim import AimConfig, AimTarget
from src.aim.targeting import (
    LOCK_MISS_TOLERANCE,
    TargetTracker,
    aim_error,
    aim_point,
    select_target,
    zone_rect,
)
from src.domain import Box, Enemy, EnemyHead, Teammate

W, H = 1000, 1000  # центр (прицел) = (500, 500)


def enemy_at(cx: float, cy: float, w: float = 40, h: float = 100) -> Enemy:
    return Enemy(body=Box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), confidence=0.9)


class TargetingTests(unittest.TestCase):
    def test_picks_nearest_enemy_in_zone(self):
        cfg = AimConfig(target=AimTarget.BODY, area_width_pct=100, area_height_pct=100)
        near, far = enemy_at(520, 500), enemy_at(800, 500)
        self.assertIs(select_target([far, near], [], W, H, cfg), near)

    def test_ignores_enemy_outside_zone(self):
        # зона 10% => ±50 px вокруг центра; враг в 300 px по x — вне зоны
        cfg = AimConfig(target=AimTarget.BODY, area_width_pct=10, area_height_pct=10)
        self.assertIsNone(select_target([enemy_at(800, 500)], [], W, H, cfg))

    def test_never_targets_when_teammate_covers_point(self):
        cfg = AimConfig(target=AimTarget.BODY, area_width_pct=100, area_height_pct=100)
        enemy = enemy_at(500, 500)
        mate = Teammate(body=Box(450, 450, 550, 550), confidence=0.9)  # накрывает точку
        self.assertIsNone(select_target([enemy], [mate], W, H, cfg))

    def test_aim_error_is_vector_to_center(self):
        cfg = AimConfig(target=AimTarget.BODY)
        ex, ey = aim_error(enemy_at(600, 500), W, H, cfg)  # центр тела (600, 500)
        self.assertAlmostEqual(ex, 100.0)
        self.assertAlmostEqual(ey, 0.0)

    def test_head_target_aims_higher_than_body(self):
        enemy = enemy_at(500, 500, h=200)  # тело по y: 400..600
        _, body_y = aim_point(enemy, AimConfig(target=AimTarget.BODY))
        _, head_y = aim_point(enemy, AimConfig(target=AimTarget.HEAD))
        self.assertLess(head_y, body_y)  # голова выше центра тела


    def test_height_target_ignores_detected_enemy_head(self):
        enemy = enemy_at(500, 500, h=200)
        enemy.head = EnemyHead(Box(490, 390, 510, 410), confidence=0.9)
        self.assertEqual(
            aim_point(enemy, AimConfig(target=AimTarget.HEIGHT, head_y_ratio=0.25)),
            (500.0, 450.0),
        )

    def test_head_target_prefers_detected_enemy_head(self):
        enemy = enemy_at(500, 500, h=200)
        enemy.head = EnemyHead(Box(490, 390, 510, 410), confidence=0.9)
        self.assertEqual(aim_point(enemy, AimConfig(target=AimTarget.HEAD)), (500.0, 400.0))

    def test_zone_rect_centered_on_crosshair(self):
        cfg = AimConfig(area_width_pct=40, area_height_pct=50)
        self.assertEqual(zone_rect(W, H, cfg), (300.0, 250.0, 700.0, 750.0))


def _full_zone_cfg() -> AimConfig:
    return AimConfig(target=AimTarget.BODY, area_width_pct=100, area_height_pct=100)


class TargetTrackerTests(unittest.TestCase):
    def test_keeps_locked_enemy_when_other_becomes_closer_to_crosshair(self):
        cfg = _full_zone_cfg()
        tracker = TargetTracker()
        a, b = enemy_at(540, 500), enemy_at(700, 500)
        self.assertIs(tracker.select([a, b], [], W, H, cfg).target, a)  # лок на A
        # B стал ближе к прицелу, чем A, — но лок должен удержать A
        a2, b2 = enemy_at(550, 500), enemy_at(515, 500)
        self.assertIs(tracker.select([a2, b2], [], W, H, cfg).target, a2)

    def test_switches_target_only_after_miss_tolerance(self):
        cfg = _full_zone_cfg()
        tracker = TargetTracker()
        a, b = enemy_at(500, 500), enemy_at(900, 900)  # B дальше lock-радиуса от A
        self.assertIs(tracker.select([a, b], [], W, H, cfg).target, a)
        # A пропал: пока не исчерпан допуск — держим лок и не прыгаем на B
        for _ in range(LOCK_MISS_TOLERANCE):
            self.assertIsNone(tracker.select([b], [], W, H, cfg).target)
        # допуск исчерпан — выбираем новую цель (B)
        self.assertIs(tracker.select([b], [], W, H, cfg).target, b)

    def test_view_shift_keeps_lock_after_camera_moved(self):
        cfg = _full_zone_cfg()
        tracker = TargetTracker()
        a = enemy_at(700, 500)
        self.assertIs(tracker.select([a], [], W, H, cfg).target, a)
        # камера довернулась на 200px вправо: A теперь в центре,
        # а на старом месте A появился другой враг
        a2, b2 = enemy_at(500, 500), enemy_at(700, 500)
        sel = tracker.select([a2, b2], [], W, H, cfg, view_shift=(200.0, 0.0))
        self.assertIs(sel.target, a2)

    def test_reset_releases_lock(self):
        cfg = _full_zone_cfg()
        tracker = TargetTracker()
        a, b = enemy_at(540, 500), enemy_at(700, 500)
        self.assertIs(tracker.select([a, b], [], W, H, cfg).target, a)
        tracker.reset()
        # без лока снова действует «ближайший к прицелу»
        a2, b2 = enemy_at(550, 500), enemy_at(515, 500)
        self.assertIs(tracker.select([a2, b2], [], W, H, cfg).target, b2)

    def test_lock_acquired_only_on_fresh_lock(self):
        cfg = _full_zone_cfg()
        tracker = TargetTracker()
        a, b = enemy_at(500, 500), enemy_at(900, 900)  # B дальше lock-радиуса от A
        self.assertTrue(tracker.select([a, b], [], W, H, cfg).lock_acquired)
        self.assertFalse(tracker.select([a, b], [], W, H, cfg).lock_acquired)  # лок продолжается
        # A умер: после допуска лок переключается на B — это снова «новая цель»
        for _ in range(LOCK_MISS_TOLERANCE):
            self.assertFalse(tracker.select([b], [], W, H, cfg).lock_acquired)
        switched = tracker.select([b], [], W, H, cfg)
        self.assertIs(switched.target, b)
        self.assertTrue(switched.lock_acquired)

    def test_aim_point_follows_raw_box_without_lag(self):
        cfg = _full_zone_cfg()
        tracker = TargetTracker()
        # точка прицеливания = сырой центр залоченного бокса, без сглаживания/лага:
        # сглаживание входа регулятора давало overshoot (прицел перелетал цель)
        self.assertEqual(tracker.select([enemy_at(540, 500)], [], W, H, cfg).aim_point, (540.0, 500.0))
        self.assertEqual(tracker.select([enemy_at(548, 500)], [], W, H, cfg).aim_point, (548.0, 500.0))


if __name__ == "__main__":
    unittest.main()
