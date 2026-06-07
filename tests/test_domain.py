"""
Тесты доменных моделей.
Запуск из корня C:\\AI:  python -m unittest discover -s tests -t .

unittest — встроенный в Python фреймворк тестов (аналог NUnit/xUnit в .NET).
"""

import unittest

from src.domain import Box, Enemy


class BoxTests(unittest.TestCase):
    def test_size_and_center(self):
        b = Box(x1=10, y1=20, x2=30, y2=60)
        self.assertEqual(b.width, 20)
        self.assertEqual(b.height, 40)
        self.assertEqual(b.center, (20.0, 40.0))


class EnemyTests(unittest.TestCase):
    def test_aim_point_prefers_head(self):
        enemy = Enemy(
            body=Box(0, 0, 100, 200),
            head=Box(40, 0, 60, 20),
            confidence=0.9,
        )
        self.assertEqual(enemy.aim_point, (50.0, 10.0))  # центр головы

    def test_aim_point_falls_back_to_body(self):
        enemy = Enemy(body=Box(0, 0, 100, 200), confidence=0.8)
        self.assertEqual(enemy.aim_point, (50.0, 100.0))  # центр тела


if __name__ == "__main__":
    unittest.main()
