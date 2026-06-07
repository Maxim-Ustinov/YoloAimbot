"""Доменная модель врага (Enemy)."""

from dataclasses import dataclass

from .geometry import Box


@dataclass
class Enemy:
    """
    Один обнаруженный враг.

    Способ детекции выбран как «враг + голова» (2 класса YOLO):
      • body  — бокс всего силуэта (класс 'enemy'). Обязателен: это «якорь»,
                без него врага нет.
      • head  — отдельный бокс (класс 'head'). Может быть None, если голову
                не видно или детектор её не нашёл.
      • legs  — пока отдельно не детектим. Задел на будущее (выведем из нижней
                части body, если понадобится). По умолчанию None.

    confidence — уверенность детектора для тела, 0..1.
    """

    body: Box
    head: Box | None = None
    legs: Box | None = None
    confidence: float = 0.0

    @property
    def aim_point(self) -> tuple[float, float]:
        """
        Куда целиться. Приоритет — голова (хедшот);
        если головы нет — центр тела.
        """
        target = self.head if self.head is not None else self.body
        return target.center
