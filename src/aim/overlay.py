"""Состояние для GUI-оверлея: что аимбот видит и куда целится в текущем кадре.

Контроллер собирает OverlayState на каждом обработанном кадре и атомарно
заменяет ссылку (AimController.overlay_state); GUI-поток читает последнее
состояние и рисует его поверх игры. Здесь только чистые данные без tkinter —
сборка тестируется без GUI и без модели.
"""

from dataclasses import dataclass

from src.domain import Enemy, Teammate

from .config import AimConfig
from .targeting import zone_rect

BoxTuple = tuple[float, float, float, float]  # x1, y1, x2, y2


def _as_tuple(box) -> BoxTuple:
    return (box.x1, box.y1, box.x2, box.y2)


@dataclass(frozen=True)
class OverlayState:
    """Боксы — в пикселях кадра захвата; region — положение кадра на экране."""

    region: tuple[int, int, int, int]  # left, top, width, height
    enemies: list[BoxTuple]
    heads: list[BoxTuple]
    teammates: list[BoxTuple]
    target_box: BoxTuple | None
    aim_point: tuple[float, float] | None
    zone: BoxTuple
    timestamp: float
    inference_ms: float = 0.0  # время детекта (детектор), сглаженное
    fps: float = 0.0           # частота цикла наводки, сглаженная


def build_overlay_state(
    enemies: list[Enemy],
    teammates: list[Teammate],
    target: Enemy | None,
    target_point: tuple[float, float] | None,
    config: AimConfig,
    frame_w: int,
    frame_h: int,
    origin: tuple[int, int],
    timestamp: float,
    inference_ms: float = 0.0,
    fps: float = 0.0,
) -> OverlayState:
    """origin — экран. координаты левого верхнего угла кадра захвата;
    target_point — сглаженная точка прицеливания от трекера (куда реально целимся).
    """
    return OverlayState(
        region=(origin[0], origin[1], frame_w, frame_h),
        enemies=[_as_tuple(enemy.body) for enemy in enemies],
        heads=[_as_tuple(enemy.head) for enemy in enemies if enemy.head is not None],
        teammates=[_as_tuple(mate.body) for mate in teammates],
        target_box=_as_tuple(target.body) if target is not None else None,
        aim_point=target_point if target is not None else None,
        zone=zone_rect(frame_w, frame_h, config),
        timestamp=timestamp,
        inference_ms=inference_ms,
        fps=fps,
    )
