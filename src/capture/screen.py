"""Захват экрана через bettercam (Desktop Duplication API)."""

import threading

import bettercam
import numpy as np
from bettercam.bettercam import BetterCam

_BETTERCAM_PATCHED = False


def _patch_bettercam_lifecycle() -> None:
    """Делает stop/release BetterCam идемпотентными для аварийного рестарта.

    В bettercam 1.x внутренний поток при ошибке вызывает self.stop(), а stop()
    пытается join-ить этот же поток. Это печатает RuntimeError и оставляет объект
    в factory-cache. Патч повторяет штатную очистку, но пропускает self-join.
    """
    global _BETTERCAM_PATCHED
    if _BETTERCAM_PATCHED:
        return

    def safe_stop(self):
        frame_available = getattr(self, "_BetterCam__frame_available", None)
        stop_capture = getattr(self, "_BetterCam__stop_capture", None)
        thread = getattr(self, "_BetterCam__thread", None)
        if getattr(self, "is_capturing", False):
            if frame_available is not None:
                frame_available.set()
            if stop_capture is not None:
                stop_capture.set()
            if thread is not None and threading.current_thread() is not thread:
                thread.join(timeout=10)
        self.is_capturing = False
        setattr(self, "_BetterCam__frame_buffer", None)
        setattr(self, "_BetterCam__frame_count", 0)
        if frame_available is not None:
            frame_available.clear()
        if stop_capture is not None:
            stop_capture.clear()

    def safe_release(self):
        try:
            self.stop()
        except Exception:
            pass
        duplicator = getattr(self, "_duplicator", None)
        if duplicator is not None:
            try:
                duplicator.release()
            except Exception:
                pass
        stagesurf = getattr(self, "_stagesurf", None)
        if stagesurf is not None:
            try:
                stagesurf.release()
            except Exception:
                pass

    BetterCam.stop = safe_stop
    BetterCam.release = safe_release
    _BETTERCAM_PATCHED = True


def _forget_bettercam_instance(camera) -> None:
    factory = bettercam.__dict__.get("__factory")
    instances = getattr(factory, "_camera_instances", None)
    if instances is None:
        return
    for key, value in list(instances.items()):
        if value is camera:
            instances.pop(key, None)


class ScreenCapture:
    """
    Быстрый захват экрана. Работает через фоновый поток bettercam:
    после start() кадры готовятся непрерывно, latest_frame() отдаёт последний.

    Кадр — numpy-массив формы (высота, ширина, 3), каналы в порядке BGR
    (как в OpenCV и как ждёт ultralytics).

    region — область экрана (left, top, right, bottom) в пикселях;
             None = весь основной монитор.
    """

    def __init__(
        self,
        region: tuple[int, int, int, int] | None = None,
        target_fps: int = 144,
    ):
        _patch_bettercam_lifecycle()
        self._camera = bettercam.create(output_color="BGR")
        self._region = region
        self._target_fps = target_fps

    def start(self) -> None:
        if self._camera is None:
            _patch_bettercam_lifecycle()
            self._camera = bettercam.create(output_color="BGR")
        self._camera.start(
            region=self._region,
            target_fps=self._target_fps,
            video_mode=True,
        )

    def latest_frame(self, timeout: float = 1.0):
        """Последний кадр (numpy BGR).

        bettercam.get_latest_frame() ждёт без таймаута. Если внутренний поток
        захвата умер, контроллер зависал навсегда. Здесь ждём ограниченно и
        явно сообщаем, что захват остановился.
        """
        if self._camera is None:
            raise RuntimeError("screen capture is closed")
        event = getattr(self._camera, "_BetterCam__frame_available", None)
        if event is None:
            return self._camera.get_latest_frame()

        if not event.wait(timeout):
            stop_event = getattr(self._camera, "_BetterCam__stop_capture", None)
            thread = getattr(self._camera, "_BetterCam__thread", None)
            stopped = stop_event is not None and stop_event.is_set()
            dead_thread = thread is not None and not thread.is_alive()
            if stopped or dead_thread or not getattr(self._camera, "is_capturing", False):
                raise RuntimeError("screen capture stopped")
            return None

        lock = getattr(self._camera, "_BetterCam__lock")
        with lock:
            frame_buffer = getattr(self._camera, "_BetterCam__frame_buffer")
            if frame_buffer is None:
                raise RuntimeError("screen capture buffer is closed")
            head = getattr(self._camera, "_BetterCam__head")
            frame = frame_buffer[(head - 1) % self._camera.max_buffer_len]
            event.clear()
        return np.array(frame)

    def close(self) -> None:
        """Останавливает захват и освобождает ресурсы (вызывать перед выходом).

        release() внутри bettercam дёргает stop() и освобождает COM-объекты
        (duplicator, stagesurf) прямо сейчас, пока среда жива — иначе их
        финализация при выходе из процесса падает с access violation.
        """
        try:
            camera = self._camera
            if camera is None:
                return
            self._camera = None
            try:
                camera.release()
            finally:
                _forget_bettercam_instance(camera)
        except Exception as exc:
            print(f"[capture] close ignored: {exc}")
