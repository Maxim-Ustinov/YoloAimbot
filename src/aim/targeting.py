"""Target selection and aim error math."""

import math
from dataclasses import dataclass

from src.domain import Box, Enemy, Teammate

from .config import AimConfig, AimTarget

DEFAULT_HEAD_Y_RATIO = 0.25

# Target lock: how far (as a fraction of the frame diagonal) the locked enemy may
# move between frames and still be treated as the same enemy.
LOCK_RADIUS_FRAC = 0.25
# How many consecutive frames the locked enemy may be missing (detector flicker)
# before the lock is released and a new target is picked.
LOCK_MISS_TOLERANCE = 5


@dataclass(frozen=True)
class TargetSelection:
    target: Enemy | None
    enemies: int
    teammates: int
    candidates: int
    outside_zone: int
    covered_by_teammate: int
    locked: bool = False
    # locked target's aim point in frame pixels; None when target is None
    aim_point: tuple[float, float] | None = None
    # True only on the frame when a NEW lock was acquired (fresh target)
    lock_acquired: bool = False


def aim_point(enemy: Enemy, config: AimConfig) -> tuple[float, float]:
    """Point inside the enemy box that the aim engine should move toward."""
    body = enemy.body
    if config.target == AimTarget.BODY:
        return body.center

    cx = (body.x1 + body.x2) / 2
    ratio = max(0.05, min(0.50, getattr(config, "head_y_ratio", DEFAULT_HEAD_Y_RATIO)))
    height_point = (cx, body.y1 + body.height * ratio)
    if config.target == AimTarget.HEIGHT:
        return height_point
    if config.target == AimTarget.HEAD:
        return enemy.head.center if enemy.head is not None else height_point
    return height_point


def zone_rect(
    screen_w: int, screen_h: int, config: AimConfig
) -> tuple[float, float, float, float]:
    """Detection-zone rectangle (x1, y1, x2, y2) centered on the crosshair."""
    half_w = config.area_width_pct / 100.0 * screen_w / 2
    half_h = config.area_height_pct / 100.0 * screen_h / 2
    cx, cy = screen_w / 2, screen_h / 2
    return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)


def _in_zone(point: tuple[float, float], screen_w: int, screen_h: int, config: AimConfig) -> bool:
    x1, y1, x2, y2 = zone_rect(screen_w, screen_h, config)
    px, py = point
    return x1 <= px <= x2 and y1 <= py <= y2


def _point_in_box(point: tuple[float, float], box: Box) -> bool:
    px, py = point
    return box.x1 <= px <= box.x2 and box.y1 <= py <= box.y2


def select_target(
    enemies: list[Enemy],
    teammates: list[Teammate],
    screen_w: int,
    screen_h: int,
    config: AimConfig,
) -> Enemy | None:
    """Nearest enemy in the configured zone, not covered by a teammate box."""
    return select_target_with_debug(enemies, teammates, screen_w, screen_h, config).target


def _valid_candidates(
    enemies: list[Enemy],
    teammates: list[Teammate],
    screen_w: int,
    screen_h: int,
    config: AimConfig,
) -> tuple[list[tuple[Enemy, tuple[float, float]]], int, int]:
    """Enemies whose aim point is inside the zone and not covered by a teammate."""
    candidates: list[tuple[Enemy, tuple[float, float]]] = []
    outside_zone = covered_by_teammate = 0
    for enemy in enemies:
        point = aim_point(enemy, config)
        if not _in_zone(point, screen_w, screen_h, config):
            outside_zone += 1
            continue
        if any(_point_in_box(point, mate.body) for mate in teammates):
            covered_by_teammate += 1
            continue
        candidates.append((enemy, point))
    return candidates, outside_zone, covered_by_teammate


def _nearest(
    candidates: list[tuple[Enemy, tuple[float, float]]],
    point: tuple[float, float],
) -> tuple[Enemy | None, tuple[float, float] | None, float]:
    """Candidate whose aim point is nearest to `point`: (enemy, aim point, distance)."""
    best: Enemy | None = None
    best_point: tuple[float, float] | None = None
    best_dist = float("inf")
    for enemy, p in candidates:
        dist = math.hypot(p[0] - point[0], p[1] - point[1])
        if dist < best_dist:
            best, best_point, best_dist = enemy, p, dist
    return best, best_point, best_dist


def select_target_with_debug(
    enemies: list[Enemy],
    teammates: list[Teammate],
    screen_w: int,
    screen_h: int,
    config: AimConfig,
) -> TargetSelection:
    """Select a target and report why detected enemies were rejected."""
    candidates, outside_zone, covered_by_teammate = _valid_candidates(
        enemies, teammates, screen_w, screen_h, config
    )
    best, _, _ = _nearest(candidates, (screen_w / 2, screen_h / 2))
    return TargetSelection(
        target=best,
        enemies=len(enemies),
        teammates=len(teammates),
        candidates=len(candidates),
        outside_zone=outside_zone,
        covered_by_teammate=covered_by_teammate,
    )


class TargetTracker:
    """Sticky target selection: lock onto one enemy and follow it across frames.

    Stateless per-frame "nearest to crosshair" flip-flops between two enemies:
    our own mouse move (plus bbox noise) keeps changing which one is nearest,
    so the aim jerks back and forth. The tracker locks the first selected enemy
    and keeps choosing the candidate nearest to its predicted position until it
    disappears for LOCK_MISS_TOLERANCE frames; only then a new target is picked.

    `view_shift` — how many pixels the scene moved in the frame since the last
    call because of our own mouse move (≈ mouse counts * sensitivity); the
    locked point is predicted at `last point - view_shift`.
    """

    def __init__(
        self,
        lock_radius_frac: float = LOCK_RADIUS_FRAC,
        miss_tolerance: int = LOCK_MISS_TOLERANCE,
    ):
        self._lock_radius_frac = lock_radius_frac
        self._miss_tolerance = miss_tolerance
        self._locked_point: tuple[float, float] | None = None
        self._misses = 0

    def reset(self) -> None:
        self._locked_point = None
        self._misses = 0

    def select(
        self,
        enemies: list[Enemy],
        teammates: list[Teammate],
        screen_w: int,
        screen_h: int,
        config: AimConfig,
        view_shift: tuple[float, float] = (0.0, 0.0),
    ) -> TargetSelection:
        candidates, outside_zone, covered_by_teammate = _valid_candidates(
            enemies, teammates, screen_w, screen_h, config
        )
        counts = dict(
            enemies=len(enemies),
            teammates=len(teammates),
            candidates=len(candidates),
            outside_zone=outside_zone,
            covered_by_teammate=covered_by_teammate,
        )

        if self._locked_point is not None:
            predicted = (
                self._locked_point[0] - view_shift[0],
                self._locked_point[1] - view_shift[1],
            )
            best, best_point, best_dist = _nearest(candidates, predicted)
            radius = self._lock_radius_frac * math.hypot(screen_w, screen_h)
            if best is not None and best_dist <= radius:
                self._locked_point = best_point
                self._misses = 0
                return TargetSelection(
                    target=best, aim_point=best_point, locked=True, **counts
                )
            # Locked enemy not seen this frame: hold instead of jumping to the
            # other enemy, so detector flicker does not cause target switching.
            self._misses += 1
            if self._misses <= self._miss_tolerance:
                self._locked_point = predicted
                return TargetSelection(target=None, locked=True, **counts)
            self.reset()

        best, best_point, _ = _nearest(candidates, (screen_w / 2, screen_h / 2))
        if best is None:
            return TargetSelection(target=None, **counts)
        self._locked_point = best_point
        self._misses = 0
        return TargetSelection(
            target=best, aim_point=best_point, locked=True, lock_acquired=True, **counts
        )


def aim_error(enemy: Enemy, screen_w: int, screen_h: int, config: AimConfig) -> tuple[float, float]:
    """Vector from the crosshair/frame center to the selected aim point."""
    px, py = aim_point(enemy, config)
    return px - screen_w / 2, py - screen_h / 2
