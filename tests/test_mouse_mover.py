"""Тесты доводчика мыши (SmoothMover) — пошаговая логика без фонового потока.
Запуск из корня:  python -m unittest discover -s tests -t .
"""

import unittest

from src.aim.mouse_mover import SmoothMover


class SmoothMoverTests(unittest.TestCase):
    def _mover_with_log(self, result: int = 1):
        sent: list[tuple[int, int]] = []

        def move(dx, dy):
            sent.append((dx, dy))
            return result

        return SmoothMover(move), sent

    def test_spreads_correction_into_micro_steps(self):
        mover, sent = self._mover_with_log()
        mover.set_correction(100, 0)
        for _ in range(60):
            mover._step_once()
        xs = [dx for dx, _ in sent]
        self.assertEqual(sum(xs), 100)        # довели всё, без потерь на округлении
        self.assertGreaterEqual(len(xs), 10)  # размазано на много микрошагов
        self.assertEqual(xs[0], 30)           # ease 0.3: первый шаг = 30% остатка
        self.assertTrue(all(0 < dx <= 30 for dx in xs))  # затухает, не прыгает
        self.assertEqual(mover.consume_moved(), (100, 0))

    def test_new_correction_replaces_old(self):
        mover, sent = self._mover_with_log()
        mover.set_correction(100, 0)
        mover._step_once()  # 30
        mover._step_once()  # 21
        mover.set_correction(10, 0)  # свежая детекция заменяет недоехавший остаток
        for _ in range(30):
            mover._step_once()
        self.assertEqual(sum(dx for dx, _ in sent), 30 + 21 + 10)

    def test_clear_stops_motion(self):
        mover, sent = self._mover_with_log()
        mover.set_correction(100, 50)
        mover.clear()
        for _ in range(10):
            mover._step_once()
        self.assertEqual(sent, [])

    def test_failed_sends_are_counted(self):
        mover, _sent = self._mover_with_log(result=0)
        mover.set_correction(10, 0)
        mover._step_once()
        self.assertEqual(mover.consume_moved(), (0, 0))
        self.assertEqual(mover.consume_failed(), 1)

    def test_negative_and_diagonal_corrections(self):
        mover, sent = self._mover_with_log()
        mover.set_correction(-40, 20)
        for _ in range(60):
            mover._step_once()
        self.assertEqual(sum(dx for dx, _ in sent), -40)
        self.assertEqual(sum(dy for _, dy in sent), 20)


if __name__ == "__main__":
    unittest.main()
