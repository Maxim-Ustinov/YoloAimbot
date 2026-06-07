r"""GUI-клиент аимбота на CustomTkinter — редактирует AimConfig.

Запуск из корня C:\AI:  python -m src.gui.app

Сейчас это панель настроек: контролы двусторонне связаны с объектом AimConfig,
есть сохранение/загрузка пресета (JSON). Кнопку Start (запуск наводки)
подключим следующим шагом.
"""

import json
from dataclasses import asdict
from pathlib import Path

import customtkinter as ctk

from src.aim import Activation, AimConfig, AimMode, AimTarget

PRESET = Path("aim_config.json")

TARGETS = {"Head (откат в тело)": AimTarget.HEAD, "Body": AimTarget.BODY}
ACTIVATIONS = {"Hold (зажать клавишу)": Activation.HOLD, "Always on": Activation.ALWAYS}
MODES = {"Auto": AimMode.AUTO, "Flick": AimMode.FLICK, "Smooth": AimMode.SMOOTH}


def _label_for(mapping: dict, value) -> str:
    """display-строка по значению enum."""
    for k, v in mapping.items():
        if v == value:
            return k
    return next(iter(mapping))


class AimbotGUI(ctk.CTk):
    def __init__(self, config: AimConfig | None = None):
        super().__init__()
        self.cfg = config or AimConfig()
        self._controls: dict = {}

        self.title("AssaultCube AI Aimbot")
        self.geometry("460x740")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self._build()

    # ---------- построение UI ----------
    def _build(self) -> None:
        ctk.CTkLabel(self, text="AI Aimbot — настройки",
                     font=("", 18, "bold")).pack(pady=(12, 4))
        self.body = ctk.CTkScrollableFrame(self)
        self.body.pack(fill="both", expand=True, padx=6, pady=6)

        self.enabled_var = ctk.BooleanVar(value=self.cfg.enabled)
        ctk.CTkSwitch(self.body, text="Включён (master On/Off)", variable=self.enabled_var,
                      command=lambda: setattr(self.cfg, "enabled", self.enabled_var.get())
                      ).pack(anchor="w", padx=6, pady=6)

        self._option("Цель (Aim target)", TARGETS, "target")
        self._option("Активация", ACTIVATIONS, "activation")
        self._entry("Клавиша активации (для Hold)", "activation_key")
        self._option("Режим наводки", MODES, "mode")

        self._slider("Detection area — ширина, %", 0, 100, "area_width_pct", "{:.0f}")
        self._slider("Detection area — высота, %", 0, 100, "area_height_pct", "{:.0f}")
        self._slider("Порог флика, % высоты", 0, 50, "flick_threshold_pct", "{:.0f}")
        self._slider("Speed (скорость)", 0, 1, "speed")
        self._slider("Intensity (жёсткость)", 0, 1, "intensity")
        self._slider("Sensitivity (калибровка)", 0, 3, "sensitivity")
        self._slider("Jitter (реализм)", 0, 1, "jitter")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(btns, text="Сохранить пресет", command=self._save).pack(
            side="left", expand=True, padx=4)
        ctk.CTkButton(btns, text="Загрузить", command=self._load).pack(
            side="left", expand=True, padx=4)

        self.status = ctk.CTkLabel(self, text="Start подключим следующим шагом",
                                   text_color="gray")
        self.status.pack(pady=(0, 8))

    def _option(self, label: str, mapping: dict, attr: str) -> None:
        frame = ctk.CTkFrame(self.body)
        frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(frame, text=label).pack(anchor="w")
        var = ctk.StringVar(value=_label_for(mapping, getattr(self.cfg, attr)))
        ctk.CTkOptionMenu(frame, values=list(mapping), variable=var,
                          command=lambda choice: setattr(self.cfg, attr, mapping[choice])
                          ).pack(fill="x", pady=(2, 0))
        self._controls[attr] = ("option", var, mapping)

    def _entry(self, label: str, attr: str) -> None:
        frame = ctk.CTkFrame(self.body)
        frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkLabel(frame, text=label).pack(anchor="w")
        var = ctk.StringVar(value=getattr(self.cfg, attr))
        var.trace_add("write", lambda *_: setattr(self.cfg, attr, var.get()))
        ctk.CTkEntry(frame, textvariable=var).pack(fill="x", pady=(2, 0))
        self._controls[attr] = ("entry", var, None)

    def _slider(self, label: str, lo: float, hi: float, attr: str, fmt: str = "{:.2f}") -> None:
        frame = ctk.CTkFrame(self.body)
        frame.pack(fill="x", padx=6, pady=4)
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=label).pack(side="left")
        val = ctk.CTkLabel(top, text=fmt.format(getattr(self.cfg, attr)))
        val.pack(side="right")

        def on_change(v):
            setattr(self.cfg, attr, float(v))
            val.configure(text=fmt.format(float(v)))

        s = ctk.CTkSlider(frame, from_=lo, to=hi, command=on_change)
        s.set(getattr(self.cfg, attr))
        s.pack(fill="x", pady=(2, 0))
        self._controls[attr] = ("slider", s, val, fmt)

    # ---------- пресеты ----------
    def _save(self) -> None:
        PRESET.write_text(
            json.dumps(asdict(self.cfg), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        self.status.configure(text=f"Сохранено: {PRESET}")

    def _load(self) -> None:
        if not PRESET.exists():
            self.status.configure(text="Пресета нет")
            return
        data = json.loads(PRESET.read_text(encoding="utf-8"))
        data["target"] = AimTarget(data["target"])
        data["activation"] = Activation(data["activation"])
        data["mode"] = AimMode(data["mode"])
        self.cfg = AimConfig(**data)
        self._refresh()
        self.status.configure(text=f"Загружено: {PRESET}")

    def _refresh(self) -> None:
        self.enabled_var.set(self.cfg.enabled)
        for attr, ref in self._controls.items():
            kind = ref[0]
            value = getattr(self.cfg, attr)
            if kind == "slider":
                _, s, val, fmt = ref
                s.set(value)
                val.configure(text=fmt.format(value))
            elif kind == "option":
                _, var, mapping = ref
                var.set(_label_for(mapping, value))
            elif kind == "entry":
                _, var, _u = ref
                var.set(value)


def main() -> None:
    AimbotGUI().mainloop()


if __name__ == "__main__":
    main()
