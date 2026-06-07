"""Доменные модели (аналог папки с POCO/record-классами в C#)."""

from .enemy import Enemy
from .geometry import Box
from .teammate import Teammate

__all__ = ["Box", "Enemy", "Teammate"]
