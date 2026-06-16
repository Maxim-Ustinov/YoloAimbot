"""Доменные модели (аналог папки с POCO/record-классами в C#)."""

from .enemy import Enemy
from .enemy_head import EnemyHead
from .geometry import Box
from .teammate import Teammate

__all__ = ["Box", "Enemy", "EnemyHead", "Teammate"]
