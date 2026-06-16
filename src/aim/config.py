"""Конфиг аимбота — все настраиваемые параметры наводки.

Это просто данные (как POCO/record в C#). Логика наводки будет в engine.py
и читает значения отсюда. GUI (CustomTkinter) будет редактировать этот объект.
"""

from dataclasses import dataclass
from enum import Enum


class AimTarget(str, Enum):
    """Куда наводиться."""

    BODY = "body"  # всегда в тело
    HEAD = "head"  # detected EnemyHead; if missing, falls back to the height ratio
    HEIGHT = "height"  # point by height inside the enemy bbox


class Activation(str, Enum):
    """Как включается наводка."""

    HOLD = "hold"      # наводит, только пока зажата клавиша activation_key
    ALWAYS = "always"  # наводит всегда, когда цель в зоне детекции


class AimMode(str, Enum):
    """Характер движения к цели."""

    AUTO = "auto"      # далеко от прицела → флик, близко → smooth (в одном цикле)
    FLICK = "flick"    # всегда резкий рывок
    SMOOTH = "smooth"  # всегда плавно


class MouseBackend(str, Enum):
    """Как отправлять движение мыши в систему."""

    SENDINPUT = "sendinput"
    INTERCEPTION = "interception"
    LOGITECH = "logitech"


@dataclass
class AimConfig:
    # --- что считать целью ---
    target: AimTarget = AimTarget.HEAD
    # В режиме HEAD целимся в эту долю высоты bbox от верхнего края.
    # 0.15 = выше, 0.25..0.30 = ниже и стабильнее для неточных боксов.
    head_y_ratio: float = 0.25

    # --- детектор ---
    detector_model: str = "auto"  # auto | assaultcube_640.pt | assaultcube_320.pt | путь к .pt
    detector_conf: float = 0.4
    detector_imgsz: int = 640
    capture_fps: int = 144
    # 0 = полный экран. Если задано >0, захват центрируется вокруг прицела.
    detection_window_width: int = 384
    detection_window_height: int = 216

    # --- зона детекции (прямоугольник по центру экрана = вокруг прицела) ---
    # Цель учитывается, только если её точка прицеливания внутри зоны.
    # Значения — проценты от ширины/высоты экрана (0..100). 100×100 = весь экран.
    area_width_pct: float = 40.0
    area_height_pct: float = 50.0

    # --- активация ---
    activation: Activation = Activation.HOLD
    activation_key: str = "mouse_right"  # что удерживать в режиме HOLD
    exit_hotkey: str = "f2"
    pause_hotkey: str = "f3"
    reload_config_hotkey: str = "f4"

    # --- вывод движения мыши ---
    mouse_backend: MouseBackend = MouseBackend.SENDINPUT
    interception_mouse_index: int = 1  # номер из identify.exe: INTERCEPTION_MOUSE(index)
    # дробить вывод на микрошаги ~240 Гц (SmoothMover): движение плавное,
    # без рывка раз в кадр инференса. False = слать коррекцию одним событием.
    smooth_mouse: bool = True

    # --- характер наводки ---
    mode: AimMode = AimMode.AUTO
    # В режиме AUTO: если цель дальше этого расстояния от прицела
    # (в % от высоты экрана) — делаем флик, иначе ведём smooth.
    flick_threshold_pct: float = 15.0

    # --- сила и скорость (здесь легко перепутать смысл, поэтому подробно) ---
    # speed — UI-шкала 0..5000 как в панели: 5000 = весь оставшийся вектор за тик,
    #         2500 = половина, 3200 = 64% в smooth-режиме.
    speed: float = 3200.0
    # intensity — UI-шкала 0..100: множитель силы наведения после speed.
    intensity: float = 85.0
    # sensitivity — делитель движения мыши: 3.0 значит dx/dy будут поделены на 3
    #               (как в описании на референсном интерфейсе).
    sensitivity: float = 3.0
    # max_step_px — ограничение одного движения мыши. 0 = без ограничения.
    max_step_px: float = 0.0
    # prediction_ms — упреждение: на сколько мс вперёд экстраполировать позицию
    # цели по её скорости в кадре. Компенсирует задержку пайплайна (~35 мс
    # инференс), из-за которой при повороте бокс/наводка отстают от цели.
    # 0 = выкл. Разумно ~30..40 (≈ задержка пайплайна).
    prediction_ms: float = 0.0

    # --- триггербот (автовыстрел) ---
    trigger_enabled: bool = False
    # стреляем, когда точка прицеливания ближе этого радиуса к прицелу (px)
    trigger_radius_px: float = 8.0
    # минимальная пауза между выстрелами, мс
    trigger_interval_ms: float = 150.0

    # --- реализм («жёстко, но не робот») ---
    # jitter — Random range, px: амплитуда плавного случайного дрейфа прицела.
    jitter: float = 0.0
    # задержка «реакции» при появлении новой цели, мс (0 = выкл);
    # фактическая задержка случайна в пределах ±30% от значения
    reaction_time_ms: float = 0.0

    # --- глобальный выключатель (On/Off всего аимбота) ---
    enabled: bool = True
    show_target_polygon: bool = True
