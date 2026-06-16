"""Инференс: обученная YOLO превращает кадр в доменные объекты.

Связывает AssaultCube-веса детектора с доменом.
Классы датасета: 0=enemy, 1=teammate, 2=enemy_head (у старых весов головы нет).
"""

from pathlib import Path

from ultralytics import YOLO

from src.domain import Box, Enemy, EnemyHead, Teammate

ENEMY_CLASS = 0
TEAMMATE_CLASS = 1
ENEMY_HEAD_CLASS = 2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSAULTCUBE_MAIN_WEIGHTS = PROJECT_ROOT / "assaultcube.pt"
ASSAULTCUBE_640_WEIGHTS = PROJECT_ROOT / "assaultcube_640.pt"
DEFAULT_WEIGHTS = ASSAULTCUBE_MAIN_WEIGHTS if ASSAULTCUBE_MAIN_WEIGHTS.exists() else ASSAULTCUBE_640_WEIGHTS


def _prefer_engine(weights: Path) -> Path:
    """Если рядом есть АКТУАЛЬНЫЙ TensorRT .engine — грузим его (инференс ~4× быстрее).

    Engine привязан к конкретным весам, поэтому используем его, только если он не
    старше .pt (иначе .pt переэкспортировали/сменили — engine устарел, грузим .pt).
    """
    if weights.suffix == ".engine":
        return weights
    engine = weights.with_suffix(".engine")
    try:
        if engine.exists() and engine.stat().st_mtime >= weights.stat().st_mtime:
            return engine
    except OSError:
        pass
    return weights


def resolve_weights(model: str | Path | None) -> Path:
    """Преобразует выбор из GUI/конфига в путь к весам YOLO ("auto" = основные веса)."""
    if model is None or str(model).strip().lower() in ("", "auto"):
        return _prefer_engine(DEFAULT_WEIGHTS)
    path = Path(model)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return _prefer_engine(path)


def _default_device() -> str:
    """CUDA, если доступна, иначе CPU — чтобы без NVIDIA инференс не падал каждый кадр."""
    try:
        import torch

        if torch.cuda.is_available():
            return "0"
    except Exception:
        pass
    return "cpu"


def _build_role_map(names) -> dict[int, str]:
    """class_id → роль (enemy/teammate/head) по ИМЕНИ класса.

    Работает и для наших весов (enemy/teammate/EnemyHead), и для сторонних моделей
    (player/bot/teammate_nickname/head/weapon/smoke/...): нерелевантные классы
    (weapon, smoke, fire, dead_body, hideout_target, ...) просто игнорируются.
    """
    try:
        items = list(names.items())
    except AttributeError:
        items = list(enumerate(names))
    role: dict[int, str] = {}
    for i, name in items:
        n = str(name).lower()
        if "head" in n:
            role[int(i)] = "head"
        elif "teammate" in n or "ally" in n or "friend" in n:
            role[int(i)] = "teammate"
        elif "enemy" in n or "player" in n or n == "bot" or "opponent" in n:
            role[int(i)] = "enemy"
    if not role:  # незнакомая схема имён — откат на старую 0/1/2
        role = {ENEMY_CLASS: "enemy", TEAMMATE_CLASS: "teammate", ENEMY_HEAD_CLASS: "head"}
    return role


class Detector:
    """Обёртка над YOLO: один раз грузит веса, на каждый кадр отдаёт врагов и союзников."""

    def __init__(
        self,
        weights: str | Path | None = None,
        conf: float = 0.5,
        imgsz: int = 640,
        device: str | None = None,
    ):
        self._model_choice = "auto" if weights is None else str(weights)
        weights = resolve_weights(weights)
        self._model = self._load_model(weights)
        self._role_map = _build_role_map(getattr(self._model, "names", {}))
        self._weights = weights
        self._conf = conf
        self._imgsz = imgsz
        self._device = device if device is not None else _default_device()

    def _load_model(self, weights: Path):
        if not weights.exists():
            raise FileNotFoundError(f"YOLO weights not found: {weights}")
        return YOLO(str(weights))

    def configure(self, conf: float, imgsz: int, model: str | Path | None = None) -> None:
        self._conf = conf
        self._imgsz = imgsz
        self._model_choice = "auto" if model is None else str(model)
        weights = resolve_weights(model)
        if weights != self._weights:
            self._model = self._load_model(weights)
            self._role_map = _build_role_map(getattr(self._model, "names", {}))
            self._weights = weights

    @property
    def weights(self) -> Path:
        return self._weights

    @property
    def imgsz(self) -> int:
        return self._imgsz

    @property
    def conf(self) -> float:
        return self._conf

    def _enabled_classes(self) -> list[int]:
        return sorted(self._role_map)

    def _attach_heads(self, enemies: list[Enemy], heads: list[EnemyHead]) -> None:
        for head in sorted(heads, key=lambda item: item.confidence, reverse=True):
            hx, hy = head.center
            candidates = [
                enemy
                for enemy in enemies
                if enemy.body.x1 <= hx <= enemy.body.x2 and enemy.body.y1 <= hy <= enemy.body.y2
            ]
            if not candidates:
                continue

            enemy = min(candidates, key=lambda item: item.body.width * item.body.height)
            current = enemy.head
            current_conf = getattr(current, "confidence", -1.0) if current is not None else -1.0
            if head.confidence >= current_conf:
                enemy.head = head

    def detect(self, frame) -> tuple[list[Enemy], list[Teammate]]:
        """frame — кадр BGR (numpy). Возвращает (враги, союзники) в пиксельных координатах кадра."""
        predict_kwargs = dict(
            conf=self._conf,
            device=self._device,
            classes=self._enabled_classes(),
            verbose=False,
        )
        # TensorRT engine собран под фиксированный размер: задавать imgsz нельзя
        # (иначе "input size != max model size"). Для .pt — берём из конфига.
        if self._weights.suffix.lower() != ".engine":
            predict_kwargs["imgsz"] = self._imgsz
        res = self._model.predict(frame, **predict_kwargs)[0]

        enemies: list[Enemy] = []
        teammates: list[Teammate] = []
        enemy_heads: list[EnemyHead] = []
        for b in res.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            box = Box(x1, y1, x2, y2)
            conf = float(b.conf[0])
            role = self._role_map.get(int(b.cls[0]))
            if role == "enemy":
                enemies.append(Enemy(body=box, confidence=conf))
            elif role == "head":
                enemy_heads.append(EnemyHead(box=box, confidence=conf))
            elif role == "teammate":
                teammates.append(Teammate(body=box, confidence=conf))
            # прочие классы (weapon/smoke/...) игнорируются

        self._attach_heads(enemies, enemy_heads)
        return enemies, teammates
