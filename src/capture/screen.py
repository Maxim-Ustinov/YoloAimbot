"""Захват экрана через bettercam (Desktop Duplication API)."""

import bettercam


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
        target_fps: int = 120,
    ):
        self._camera = bettercam.create(output_color="BGR")
        self._region = region
        self._target_fps = target_fps

    def start(self) -> None:
        self._camera.start(
            region=self._region,
            target_fps=self._target_fps,
            video_mode=True,
        )

    def latest_frame(self):
        """Последний кадр (numpy BGR). Блокирует, пока не появится новый кадр."""
        return self._camera.get_latest_frame()

    def close(self) -> None:
        """Останавливает захват и освобождает ресурсы (вызывать перед выходом).

        release() внутри bettercam дёргает stop() и освобождает COM-объекты
        (duplicator, stagesurf) прямо сейчас, пока среда жива — иначе их
        финализация при выходе из процесса падает с access violation.
        """
        self._camera.release()
