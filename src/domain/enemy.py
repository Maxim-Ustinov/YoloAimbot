"""Доменная модель врага (Enemy)."""

from dataclasses import dataclass

from .enemy_head import EnemyHead
from .geometry import Box


@dataclass
class Enemy:
    """
    Один обнаруженный враг.

      • body — бокс всего силуэта (класс 'enemy'). Обязателен: это «якорь»,
               без него врага нет.
      • head — бокс головы (класс 'enemy_head'); детектор привязывает его к телу.
               None, если голова не обнаружена (или веса без класса головы).
      • legs — пока отдельно не детектим. Задел на будущее.

    confidence — уверенность детектора для тела, 0..1.
    Куда целиться внутри врага, решает src.aim.targeting.aim_point (учитывает конфиг).
    """

    body: Box
    head: Box | EnemyHead | None = None
    legs: Box | None = None
    confidence: float = 0.0
