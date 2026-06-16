"""
Тесты доменных моделей.
Запуск из корня C:\\AI:  python -m unittest discover -s tests -t .

unittest — встроенный в Python фреймворк тестов (аналог NUnit/xUnit в .NET).
"""

import unittest

from src.domain import Box, Enemy, EnemyHead


class BoxTests(unittest.TestCase):
    def test_size_and_center(self):
        b = Box(x1=10, y1=20, x2=30, y2=60)
        self.assertEqual(b.width, 20)
        self.assertEqual(b.height, 40)
        self.assertEqual(b.center, (20.0, 40.0))


class EnemyTests(unittest.TestCase):
    def test_head_accepts_box_and_enemy_head(self):
        # head может быть и сырым Box, и типизированным EnemyHead — оба с .center
        box_head = Enemy(body=Box(0, 0, 100, 200), head=Box(40, 0, 60, 20))
        typed_head = Enemy(
            body=Box(0, 0, 100, 200),
            head=EnemyHead(Box(40, 0, 60, 20), confidence=0.95),
        )
        self.assertEqual(box_head.head.center, (50.0, 10.0))
        self.assertEqual(typed_head.head.center, (50.0, 10.0))

    def test_head_is_optional(self):
        self.assertIsNone(Enemy(body=Box(0, 0, 100, 200), confidence=0.8).head)


if __name__ == "__main__":
    unittest.main()
