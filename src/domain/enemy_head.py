"""Domain model for an enemy head box."""

from dataclasses import dataclass

from .geometry import Box


@dataclass(frozen=True)
class EnemyHead:
    """A detected enemy head attached to an enemy body."""

    box: Box
    confidence: float = 0.0

    @property
    def x1(self) -> float:
        return self.box.x1

    @property
    def y1(self) -> float:
        return self.box.y1

    @property
    def x2(self) -> float:
        return self.box.x2

    @property
    def y2(self) -> float:
        return self.box.y2

    @property
    def width(self) -> float:
        return self.box.width

    @property
    def height(self) -> float:
        return self.box.height

    @property
    def center(self) -> tuple[float, float]:
        return self.box.center
