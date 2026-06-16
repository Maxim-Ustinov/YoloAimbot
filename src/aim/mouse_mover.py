"""Фоновый «доводчик» мыши: дробит коррекцию на микрошаги с высокой частотой.

Цикл наводки выдаёт коррекцию раз в кадр инференса (~30–60 Гц). Если отправлять
её одним событием, камера движется рывками: скачок — пауза — скачок. SmoothMover
держит «остаток» коррекции и шлёт его маленькими порциями ~TICK_HZ раз в секунду
с экспоненциальным затуханием: движение непрерывное, у цели мягко тормозит.

set_correction() на каждом кадре ЗАМЕНЯЕТ остаток (свежая детекция важнее
недоехавшей старой коррекции), поэтому ошибка не накапливается.
"""

import ctypes
import threading

TICK_HZ = 240        # частота микрошагов
EASE_PER_TICK = 0.3  # доля остатка за тик: быстрый старт, плавное торможение


class SmoothMover:
    """Шлёт move_fn(dx, dy) микрошагами из фонового потока."""

    def __init__(
        self,
        move_fn,
        get_error_fn=lambda: 0,
        tick_hz: int = TICK_HZ,
        ease: float = EASE_PER_TICK,
    ):
        self._move = move_fn
        self._get_error = get_error_fn
        self._tick = 1.0 / float(tick_hz)
        self._ease = ease
        self._lock = threading.Lock()
        self._rest_x = 0.0  # сколько ещё довести, px (с дробной частью)
        self._rest_y = 0.0
        self._moved_x = 0  # фактически отправлено с последнего consume_moved()
        self._moved_y = 0
        self._failed = 0
        self.last_error = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- управление из потока наводки ----------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def set_correction(self, dx: float, dy: float) -> None:
        """Заменить остаток коррекции свежим (вызывается на каждом кадре)."""
        with self._lock:
            self._rest_x = float(dx)
            self._rest_y = float(dy)

    def clear(self) -> None:
        """Остановить остаточное движение (пауза/потеря цели)."""
        self.set_correction(0.0, 0.0)

    def consume_moved(self) -> tuple[int, int]:
        """Сколько px реально отправлено с прошлого вызова (для view_shift)."""
        with self._lock:
            moved = (self._moved_x, self._moved_y)
            self._moved_x = self._moved_y = 0
        return moved

    def consume_failed(self) -> int:
        """Сколько микрошагов не приняла система с прошлого вызова."""
        with self._lock:
            failed = self._failed
            self._failed = 0
        return failed

    # ---------- работа фонового потока ----------
    def _next_step(self) -> tuple[int, int]:
        """Вычислить и списать очередной микрошаг (под локом)."""
        with self._lock:
            step_x = round(self._rest_x * self._ease)
            step_y = round(self._rest_y * self._ease)
            # хвост меньше шага — дожимаем по 1px, чтобы доводка не зависала
            if step_x == 0 and abs(self._rest_x) >= 0.5:
                step_x = 1 if self._rest_x > 0 else -1
            if step_y == 0 and abs(self._rest_y) >= 0.5:
                step_y = 1 if self._rest_y > 0 else -1
            self._rest_x -= step_x
            self._rest_y -= step_y
        return step_x, step_y

    def _step_once(self) -> None:
        step_x, step_y = self._next_step()
        if step_x == 0 and step_y == 0:
            return
        if self._move(step_x, step_y):
            with self._lock:
                self._moved_x += step_x
                self._moved_y += step_y
        else:
            with self._lock:
                self._failed += 1
            self.last_error = self._get_error()

    def _set_timer_resolution(self, enable: bool) -> None:
        # без timeBeginPeriod(1) Event.wait(4мс) на Windows может округляться
        # до ~15.6мс, и 240 Гц превратятся в ~64 Гц
        try:
            winmm = ctypes.WinDLL("winmm")
            (winmm.timeBeginPeriod if enable else winmm.timeEndPeriod)(1)
        except Exception:
            pass

    def _run(self) -> None:
        self._set_timer_resolution(True)
        try:
            while not self._stop.is_set():
                self._step_once()
                self._stop.wait(self._tick)
        finally:
            self._set_timer_resolution(False)
