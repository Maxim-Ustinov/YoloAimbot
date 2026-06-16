"""Контроллер наводки: связывает захват экрана, инференс, выбор цели, движок и мышь.

Цикл крутится в фоновом потоке (чтобы GUI не подвисал):
    кадр (ScreenCapture) → детект (Detector → Enemy/Teammate/EnemyHead)
    → выбор врага в зоне с локом на одну цель (TargetTracker), союзники исключены
    → Aimer.step(вектор ошибки) → относительное движение мыши.

Учитывает master-выключатель (config.enabled) и активацию (HOLD по клавише / ALWAYS).
Инференс не запускается, пока наводка неактивна — GPU не греется на холостом ходу.
"""

import math
import random
import threading
import time
import ctypes

from src.capture import ScreenCapture
from src.detect import Detector

from . import hotkey
from .config import Activation, AimConfig, MouseBackend
from .engine import Aimer, should_fire
from .mouse import (
    click_left as sendinput_click_left,
    get_last_input_error,
    move_relative as sendinput_move_relative,
)
from .mouse_mover import SmoothMover
from .overlay import OverlayState, build_overlay_state
from .targeting import TargetTracker

# Плавный разгон после реакции: за сколько тиков наводки выходим на полную скорость.
RAMP_TICKS = 4


class AimController:
    def __init__(
        self,
        config: AimConfig,
        detector: Detector | None = None,
        capture: ScreenCapture | None = None,
    ):
        self.config = config
        self._detector = detector
        self._capture = capture
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._stopped = threading.Event()
        self._capture_region_desc = "full"
        # (region, fps), с которыми создан текущий capture, — чтобы на лету
        # замечать изменения Detection window / Capture FPS из GUI.
        self._capture_params: tuple | None = None
        # Последний обработанный кадр для GUI-оверлея. Пишется потоком наводки
        # атомарной заменой ссылки, читается GUI-потоком; None = нечего рисовать.
        self.overlay_state: OverlayState | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 15.0) -> bool:
        self._stop.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=timeout)
        return not (self._thread and self._thread.is_alive())

    def _active(self) -> bool:
        if not self.config.enabled:
            return False
        if self.config.activation == Activation.HOLD:
            return hotkey.is_down(self.config.activation_key)
        return True

    def _make_mouse_output(self):
        """(move_relative, click_left, close, имя, последняя ошибка) для backend'а."""
        if self.config.mouse_backend == MouseBackend.INTERCEPTION:
            from .interception_mouse import InterceptionMouse

            mouse_index = int(self.config.interception_mouse_index)
            mouse = InterceptionMouse(mouse_index=mouse_index)
            return (
                mouse.move_relative,
                mouse.click_left,
                mouse.close,
                f"interception:{mouse_index}/{mouse.open_mode}",
                lambda: mouse.last_error,
            )
        if self.config.mouse_backend == MouseBackend.LOGITECH:
            from .logitech_mouse import LogitechMouse

            mouse = LogitechMouse()
            return (
                mouse.move_relative,
                mouse.click_left,
                mouse.close,
                f"logitech/{mouse.open_mode}",
                lambda: mouse.last_error,
            )
        return (
            sendinput_move_relative,
            sendinput_click_left,
            lambda: None,
            "sendinput",
            get_last_input_error,
        )

    def _capture_fps(self) -> int:
        return max(30, min(240, int(round(float(self.config.capture_fps)))))

    def _screen_size(self) -> tuple[int, int] | None:
        try:
            user32 = ctypes.windll.user32
            return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
        except Exception:
            return None

    def _capture_region(self) -> tuple[int, int, int, int] | None:
        width = int(round(float(getattr(self.config, "detection_window_width", 0))))
        height = int(round(float(getattr(self.config, "detection_window_height", 0))))
        if width <= 0 or height <= 0:
            self._capture_region_desc = "full"
            return None
        screen_size = self._screen_size()
        if screen_size is None:
            self._capture_region_desc = "full"
            return None
        screen_w, screen_h = screen_size
        width = max(64, min(width, screen_w))
        height = max(64, min(height, screen_h))
        left = max(0, (screen_w - width) // 2)
        top = max(0, (screen_h - height) // 2)
        right = min(screen_w, left + width)
        bottom = min(screen_h, top + height)
        self._capture_region_desc = f"{right - left}x{bottom - top}"
        return (left, top, right, bottom)

    def _make_capture(self) -> ScreenCapture:
        region = self._capture_region()
        fps = self._capture_fps()
        capture = ScreenCapture(region=region, target_fps=fps)
        capture.start()
        self._capture_params = (region, fps)
        return capture

    def _run(self) -> None:
        capture: ScreenCapture | None = None
        close_mouse = lambda: None
        mover: SmoothMover | None = None
        try:
            move_relative, click_left, close_mouse, input_backend, get_input_error = (
                self._make_mouse_output()
            )
            if self.config.smooth_mouse:
                mover = SmoothMover(move_relative, get_input_error)
                mover.start()
                input_backend += "+smooth"
            imgsz = int(round(self.config.detector_imgsz / 32) * 32)
            detector = self._detector or Detector(
                weights=self.config.detector_model,
                conf=self.config.detector_conf,
                imgsz=max(320, imgsz),
            )
            if self._capture is not None:
                capture = self._capture
                self._capture_region_desc = "injected"
                capture.start()
            else:
                capture = self._make_capture()
        except Exception as exc:  # модель/захват не поднялись — сообщаем в консоль и выходим
            if mover is not None:
                mover.stop()
            close_mouse()
            if capture is not None:
                capture.close()
            print(f"[aim] не удалось запустить наводку: {exc}")
            return

        aimer: Aimer | None = None
        tracker = TargetTracker()  # лок на одну цель, чтобы аим не прыгал между врагами
        view_shift = (0.0, 0.0)  # на сколько px сцена сдвинулась из-за нашего же движения мыши
        last_log = time.monotonic()
        last_capture_check = last_log
        # гуманизация: «реакция» на новую цель + плавный разгон первых тиков
        lock_started = 0.0
        reaction_delay = 0.0
        ticks_after_reaction = 0
        # упреждение цели: оценка скорости точки прицеливания в кадре
        prev_aim: tuple[float, float] | None = None
        prev_aim_time = 0.0
        aim_vel = (0.0, 0.0)
        # триггербот
        last_shot = 0.0
        shots = 0
        frames = detections = targets = move_attempts = moves = failed_moves = 0
        enemy_detections = teammate_detections = target_candidates = lock_frames = 0
        zone_rejects = teammate_rejects = 0
        sum_abs_dx = sum_abs_dy = 0
        max_abs_dx = max_abs_dy = 0
        last_move = (0, 0)
        last_error = (0.0, 0.0)
        last_input_error = 0
        capture_restart_attempts = 0
        was_active = False
        detect_ms_ema = 0.0   # сглаженное время детекта, мс (для latency-оверлея)
        fps_ema = 0.0         # сглаженный FPS цикла наводки
        last_frame_t = 0.0
        try:
            while not self._stop.is_set():
                active = self._active()
                # Оверлей-превью: когда оверлей включён, обрабатываем кадры и рисуем
                # детекции даже без активной наводки (HOLD не зажат) — мышь при этом
                # не двигаем. Привязано к master-выключателю: на паузе (enabled=False)
                # ничего не обрабатываем и оверлей гасим, GPU свободен.
                preview = bool(self.config.show_target_polygon) and self.config.enabled
                if not active and not preview:
                    tracker.reset()  # пауза/отпущенная клавиша: старый лок больше не актуален
                    view_shift = (0.0, 0.0)
                    if mover is not None:
                        mover.clear()  # не доводим остаток после отпускания клавиши
                        mover.consume_moved()
                    self.overlay_state = None
                    was_active = False
                    now = time.monotonic()
                    if now - last_log >= 1.0:
                        print(
                            "[aim] inactive: "
                            f"enabled={self.config.enabled}, "
                            f"activation={self.config.activation.value}, "
                            f"key={self.config.activation_key}"
                        )
                        last_log = now
                    self._stop.wait(0.005)  # простаиваем, пока наводка выключена
                    continue
                # Живое применение Detection window / Capture FPS из GUI:
                # раз в секунду сверяем желаемые параметры с текущим capture.
                if self._capture is None:
                    now = time.monotonic()
                    if now - last_capture_check >= 1.0:
                        last_capture_check = now
                        desired = (self._capture_region(), self._capture_fps())
                        if desired != self._capture_params:
                            print(
                                "[aim] применяю настройки захвата: "
                                f"window={self._capture_region_desc}, fps={desired[1]}"
                            )
                            try:
                                capture.close()
                            except Exception as close_exc:
                                print(f"[aim] ошибка при закрытии старого capture: {close_exc}")
                            try:
                                capture = self._make_capture()
                            except Exception as exc:
                                # capture закрыт: latest_frame упадёт, и штатный
                                # рестарт-механизм ниже поднимет захват заново
                                print(f"[aim] не удалось пересоздать capture: {exc}")
                                continue
                            tracker.reset()  # размер кадра мог измениться
                            view_shift = (0.0, 0.0)
                try:
                    frame = capture.latest_frame(timeout=1.0)
                except Exception as exc:
                    if self._capture is not None:
                        print(f"[aim] захват экрана остановился: {exc}")
                        break
                    capture_restart_attempts += 1
                    delay = min(2.0, 0.25 * capture_restart_attempts)
                    print(
                        "[aim] захват экрана остановился: "
                        f"{exc}; перезапуск capture через {delay:.2f}с"
                    )
                    try:
                        capture.close()
                    except Exception as close_exc:
                        print(f"[aim] ошибка при закрытии старого capture: {close_exc}")
                    if self._stop.wait(delay):
                        break
                    try:
                        capture = self._make_capture()
                    except Exception as restart_exc:
                        print(f"[aim] не удалось перезапустить capture: {restart_exc}")
                        continue
                    tracker.reset()  # размер окна захвата мог измениться — лок в старых координатах
                    view_shift = (0.0, 0.0)
                    capture_restart_attempts = 0
                    last_log = time.monotonic()
                    print(f"[aim] capture перезапущен: fps={self._capture_fps()}")
                    continue
                if frame is None:
                    continue
                capture_restart_attempts = 0
                if self._stop.is_set():
                    break
                frames += 1
                h, w = frame.shape[:2]
                # пересоздаём и при смене размера кадра: порог флика считается
                # в процентах от высоты, со старой высотой он был бы неверным
                if aimer is None or aimer.screen_height != h:
                    aimer = Aimer(self.config, screen_height=h)
                detector.configure(
                    conf=self.config.detector_conf,
                    imgsz=max(320, int(round(self.config.detector_imgsz / 32) * 32)),
                    model=self.config.detector_model,
                )
                t_detect = time.perf_counter()
                try:
                    enemies, teammates = detector.detect(frame)
                except Exception as exc:  # транзиентная ошибка инференса не должна убивать поток
                    print(f"[aim] ошибка инференса: {exc}")
                    self._stop.wait(0.05)
                    continue
                detect_ms = (time.perf_counter() - t_detect) * 1000.0
                detect_ms_ema = detect_ms if detect_ms_ema == 0 else 0.2 * detect_ms + 0.8 * detect_ms_ema
                now_t = time.perf_counter()
                if last_frame_t:
                    inst_fps = 1.0 / max(1e-3, now_t - last_frame_t)
                    fps_ema = inst_fps if fps_ema == 0 else 0.2 * inst_fps + 0.8 * fps_ema
                last_frame_t = now_t
                if self._stop.is_set():
                    break
                if active and not was_active:
                    tracker.reset()  # вернулись к наводке из превью — следующий лок = «новая цель»
                was_active = active
                if mover is not None:
                    moved_x, moved_y = mover.consume_moved()
                    failed_moves += mover.consume_failed()
                    if mover.last_error:
                        last_input_error = mover.last_error
                    # сдвиг камеры с прошлого кадра = фактически отправленные микрошаги
                    sens = max(0.1, float(self.config.sensitivity))
                    view_shift = (moved_x * sens, moved_y * sens) if active else (0.0, 0.0)
                selection = tracker.select(enemies, teammates, w, h, self.config, view_shift)
                vs_frame = view_shift  # поворот камеры этого кадра — для упреждения
                view_shift = (0.0, 0.0)
                frame_time = time.monotonic()
                if selection.lock_acquired:
                    # новая цель (в т.ч. переключение после смерти старой):
                    # имитируем «реакцию» — случайная задержка ±30%
                    lock_started = frame_time
                    reaction_delay = 0.0
                    if self.config.reaction_time_ms > 0:
                        reaction_delay = (
                            self.config.reaction_time_ms / 1000.0 * random.uniform(0.7, 1.3)
                        )
                    ticks_after_reaction = 0
                detections += selection.enemies + selection.teammates
                enemy_detections += selection.enemies
                teammate_detections += selection.teammates
                target_candidates += selection.candidates
                zone_rejects += selection.outside_zone
                teammate_rejects += selection.covered_by_teammate
                if selection.locked:
                    lock_frames += 1
                target = selection.target
                # Упреждение (latency compensation): экстраполируем точку прицеливания
                # на prediction_ms вперёд по скорости цели в кадре. Из наблюдаемого
                # смещения вычитаем собственный поворот камеры (vs_frame), чтобы упреждать
                # внешнее движение (цель + ручной поворот), а не нашу же наводку.
                aim_pt = selection.aim_point
                if target is not None and selection.aim_point is not None:
                    raw = selection.aim_point
                    if selection.lock_acquired or prev_aim is None:
                        aim_vel = (0.0, 0.0)
                    else:
                        dt = frame_time - prev_aim_time
                        if 0.0 < dt < 0.2:
                            rvx = ((raw[0] - prev_aim[0]) + vs_frame[0]) / dt
                            rvy = ((raw[1] - prev_aim[1]) + vs_frame[1]) / dt
                            aim_vel = (0.5 * rvx + 0.5 * aim_vel[0], 0.5 * rvy + 0.5 * aim_vel[1])
                        else:
                            aim_vel = (0.0, 0.0)
                    prev_aim = raw
                    prev_aim_time = frame_time
                    lead = self.config.prediction_ms / 1000.0
                    if lead > 0:
                        # затухание у прицела: упреждение помогает при повороте
                        # (цель далеко/быстро уезжает), но у прицела вносит колебания
                        # в доводку — поэтому в пределах ~40 px его гасим.
                        err = math.hypot(raw[0] - w / 2, raw[1] - h / 2)
                        fade = max(0.0, min(1.0, (err - 40.0) / 110.0))
                        aim_pt = (raw[0] + aim_vel[0] * lead * fade,
                                  raw[1] + aim_vel[1] * lead * fade)
                else:
                    prev_aim = None
                    aim_vel = (0.0, 0.0)
                if self.config.show_target_polygon:
                    params = self._capture_params
                    region = params[0] if (self._capture is None and params) else None
                    origin = (region[0], region[1]) if region else (0, 0)
                    self.overlay_state = build_overlay_state(
                        enemies, teammates, target, aim_pt, self.config,
                        w, h, origin, frame_time,
                        inference_ms=detect_ms_ema, fps=fps_ema,
                    )
                else:
                    self.overlay_state = None
                if active and target is not None:
                    targets += 1
                    ex, ey = aim_pt[0] - w / 2, aim_pt[1] - h / 2
                    if frame_time - lock_started >= reaction_delay:
                        dx, dy = aimer.step(ex, ey)
                        if self.config.reaction_time_ms > 0 and ticks_after_reaction < RAMP_TICKS:
                            # после «реакции» разгоняемся плавно, а не рывком
                            ramp = (ticks_after_reaction + 1) / RAMP_TICKS
                            dx = round(dx * ramp)
                            dy = round(dy * ramp)
                        ticks_after_reaction += 1
                        if dx or dy:
                            move_attempts += 1
                            sum_abs_dx += abs(dx)
                            sum_abs_dy += abs(dy)
                            max_abs_dx = max(max_abs_dx, abs(dx))
                            max_abs_dy = max(max_abs_dy, abs(dy))
                            last_move = (dx, dy)
                            last_error = (ex, ey)
                        if dx or dy:
                            if self._stop.is_set():
                                break
                            if mover is not None:
                                # плавный вывод: доводчик раздаст коррекцию микрошагами
                                mover.set_correction(dx, dy)
                                moves += 1
                            elif move_relative(dx, dy):
                                moves += 1
                                # наше движение повернёт камеру: сцена в следующем кадре
                                # сдвинется примерно на counts * sensitivity пикселей
                                sens = max(0.1, float(self.config.sensitivity))
                                view_shift = (dx * sens, dy * sens)
                            else:
                                failed_moves += 1
                                last_input_error = get_input_error()
                        if should_fire(math.hypot(ex, ey), frame_time, last_shot, self.config):
                            last_shot = frame_time  # rate-limit даже если клик не прошёл
                            if click_left():
                                shots += 1
                elif mover is not None:
                    # превью без наводки или цель потеряна — доводчик не дрейфует
                    mover.clear()

                now = time.monotonic()
                if now - last_log >= 1.0:
                    avg_dx = sum_abs_dx / move_attempts if move_attempts else 0.0
                    avg_dy = sum_abs_dy / move_attempts if move_attempts else 0.0
                    print(
                        f"[aim] {'active' if active else 'preview'}: "
                        f"frames={frames}, detections={detections}, "
                        f"enemy={enemy_detections}, mate={teammate_detections}, "
                        f"candidate={target_candidates}, "
                        f"zone_skip={zone_rejects}, mate_skip={teammate_rejects}, "
                        f"lock={lock_frames}, "
                        f"targets={targets}, moves={moves}/{move_attempts}, failed={failed_moves}, "
                        f"shots={shots}, "
                        f"avg_move=({avg_dx:.1f},{avg_dy:.1f}), "
                        f"max_move=({max_abs_dx},{max_abs_dy}), "
                        f"last_move={last_move}, last_error=({last_error[0]:.1f},{last_error[1]:.1f}), "
                        f"input={input_backend}, input_error={last_input_error}, "
                        f"area={self.config.area_width_pct:.0f}x{self.config.area_height_pct:.0f}%, "
                        f"target={self.config.target.value}, speed={self.config.speed:.0f}, "
                        f"force={self.config.intensity:.0f}, sensitivity={self.config.sensitivity:.2f}, "
                        f"max_step={self.config.max_step_px:.0f}, random={self.config.jitter:.0f}, "
                        f"model={detector.weights.name}, "
                        f"conf={self.config.detector_conf:.2f}, imgsz={self.config.detector_imgsz}, "
                        f"capture_fps={self.config.capture_fps:.0f}, "
                        f"window={self._capture_region_desc}"
                    )
                    last_log = now
                    frames = detections = targets = move_attempts = moves = failed_moves = 0
                    enemy_detections = teammate_detections = target_candidates = lock_frames = 0
                    zone_rejects = teammate_rejects = shots = 0
                    sum_abs_dx = sum_abs_dy = 0
                    max_abs_dx = max_abs_dy = 0
        finally:
            self.overlay_state = None
            if mover is not None:
                mover.stop()
            try:
                close_mouse()
            except Exception as exc:
                print(f"[aim] ошибка при закрытии ввода мыши: {exc}")
            try:
                capture.close()
            except Exception as exc:
                print(f"[aim] ошибка при закрытии захвата: {exc}")
            self._stopped.set()
