"""Геометрия: прямоугольный хитбокс (Box)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    """
    Прямоугольник в пиксельных координатах кадра.
    (x1, y1) — левый верхний угол, (x2, y2) — правый нижний.

    Аналогия с C#: это как record со свойствами только для чтения
    (frozen=True ≈ init-only / immutable). Создал — больше не меняешь.

    Пример: Box(x1=10, y1=20, x2=30, y2=60)
    """

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[float, float]:
        """Центр прямоугольника: (cx, cy)."""
        return (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2
