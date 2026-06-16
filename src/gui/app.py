r"""CustomTkinter settings GUI for the AssaultCube AI controller.

Run from C:\AI:
    python -m src.gui.app
"""

import json
import time
import tkinter as tk
from dataclasses import asdict, fields
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from src.aim import Activation, AimConfig, AimMode, AimTarget, MouseBackend
from src.aim import hotkey
from src.gui.overlay import OverlayWindow

PRESET = Path("aim_config.json")

TAB_NAMES = ("Ai", "Aim", "Hotkeys", "Detection window")

AIM_MODES = {"Auto": AimMode.AUTO, "Flick": AimMode.FLICK, "Smooth": AimMode.SMOOTH}
TARGET_MODES = {"EnemyHead": AimTarget.HEAD, "Enemy height": AimTarget.HEIGHT}
ACTIVATIONS = {"Hold": Activation.HOLD, "Always": Activation.ALWAYS}
MOUSE_BACKENDS = {
    "SendInput": MouseBackend.SENDINPUT,
    "Interception": MouseBackend.INTERCEPTION,
    "Logitech": MouseBackend.LOGITECH,
}
MODEL_AUTO = "AImify GEN2"

BG = "#000000"
PANEL = "#050506"
TEXT = "#f4f6fb"
MUTED = "#a1a6b2"
TRACK = "#30313a"
PILL = "#2d2f37"
TAB_BG = "#24252b"
TAB_SELECTED = "#565863"
BLUE = "#0b8dff"
BLUE_DARK = "#0067c8"
CYAN = "#00a6ff"


def _label_for(mapping: dict, value) -> str:
    for label, mapped in mapping.items():
        if mapped == value:
            return label
    return next(iter(mapping))


def _model_options() -> dict[str, str]:
    return {MODEL_AUTO: "auto"}


def _config_from_json(data: dict) -> AimConfig:
    field_names = {field.name for field in fields(AimConfig)}
    data = {key: value for key, value in data.items() if key in field_names}

    if "target" in data:
        target = AimTarget(data["target"])
        data["target"] = AimTarget.HEIGHT if target == AimTarget.BODY else target
    if "activation" in data:
        data["activation"] = Activation(data["activation"])
    if "mode" in data:
        data["mode"] = AimMode(data["mode"])
    if "mouse_backend" in data:
        data["mouse_backend"] = MouseBackend(data["mouse_backend"])
    data["detector_model"] = "auto"

    for key in (
        "detector_imgsz",
        "capture_fps",
        "detection_window_width",
        "detection_window_height",
        "interception_mouse_index",
    ):
        if key in data:
            data[key] = int(float(data[key]))
    # Migration from the earlier internal 0..1 tuning model to the UI-style
    # scales used by the current panel.
    if "speed" in data and float(data["speed"]) <= 1.0:
        data["speed"] = float(data["speed"]) * 5000.0
    if "intensity" in data and float(data["intensity"]) <= 1.0:
        data["intensity"] = float(data["intensity"]) * 100.0
    if "jitter" in data and 0.0 < float(data["jitter"]) <= 1.0:
        data["jitter"] = float(data["jitter"]) * 100.0
    return AimConfig(**data)


def _load_preset_or_default() -> AimConfig:
    if not PRESET.exists():
        return AimConfig()
    return _config_from_json(json.loads(PRESET.read_text(encoding="utf-8")))


def _pretty_key(key: str) -> str:
    normalized = key.strip().lower()
    names = {
        "mouse_left": "LeftMouseButton",
        "mouse_right": "RightMouseButton",
        "mouse_middle": "MiddleMouseButton",
        "mouse_x1": "MouseX1",
        "mouse_x2": "MouseX2",
        "ctrl": "Ctrl",
        "shift": "Shift",
        "alt": "Alt",
        "space": "Space",
        "tab": "Tab",
        "esc": "Esc",
        "escape": "Esc",
    }
    if normalized in names:
        return names[normalized]
    if normalized.startswith("f") and normalized[1:].isdigit():
        return normalized.upper()
    if len(normalized) == 1:
        return normalized.upper()
    return normalized.title() if normalized else "None"


def _key_from_event(event: tk.Event) -> str | None:
    keysym = (event.keysym or "").lower()
    aliases = {
        "shift_l": "shift",
        "shift_r": "shift",
        "control_l": "ctrl",
        "control_r": "ctrl",
        "alt_l": "alt",
        "alt_r": "alt",
        "escape": "esc",
        "space": "space",
        "tab": "tab",
        "caps_lock": "caps",
    }
    if keysym in aliases:
        return aliases[keysym]
    if keysym.startswith("f") and keysym[1:].isdigit():
        return keysym
    if event.char and len(event.char) == 1 and event.char.isprintable():
        return event.char.lower()
    return keysym or None


def _mouse_from_event(event: tk.Event) -> str | None:
    return {
        1: "mouse_left",
        2: "mouse_middle",
        3: "mouse_right",
        4: "mouse_x1",
        5: "mouse_x2",
    }.get(getattr(event, "num", 0))


class AimbotGUI(ctk.CTk):
    def __init__(self, config: AimConfig | None = None):
        super().__init__()
        self.cfg = config or _load_preset_or_default()
        self._controls: dict[str, tuple] = {}
        self._tabs: dict[str, ctk.CTkFrame] = {}
        self._controller = None
        self._paused_by_button = False
        self._pending_hotkey_attr: str | None = None
        self._hotkey_edges: dict[str, bool] = {}
        self._hotkey_allow_mouse: dict[str, bool] = {}  # можно ли назначать кнопку мыши
        self._hotkey_capture_t = 0.0  # время входа в захват (для debounce клика-входа)
        self._status_after_id: str | None = None
        self._overlay: OverlayWindow | None = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("AssaultCube AI")
        self.geometry("548x808")
        self.minsize(520, 720)
        self.configure(fg_color="#15161a")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<KeyPress>", self._capture_key, add="+")
        self.bind_all("<ButtonPress>", self._capture_mouse, add="+")

        self._build()
        self._show_tab("Ai")
        self.after(120, self._poll_hotkeys)
        self.after(150, self._poll_overlay)

    def _build(self) -> None:
        self.shell = ctk.CTkFrame(
            self,
            fg_color=BG,
            border_color=BLUE,
            border_width=1,
            corner_radius=12,
        )
        self.shell.pack(fill="both", expand=True, padx=4, pady=4)

        self.tab_var = ctk.StringVar(value="Ai")
        tabs = ctk.CTkSegmentedButton(
            self.shell,
            values=list(TAB_NAMES),
            variable=self.tab_var,
            command=self._show_tab,
            fg_color=TAB_BG,
            selected_color=TAB_SELECTED,
            selected_hover_color=TAB_SELECTED,
            unselected_color=TAB_BG,
            unselected_hover_color="#30313a",
            text_color=TEXT,
            corner_radius=9,
        )
        tabs.pack(pady=(16, 10))

        self.body = ctk.CTkScrollableFrame(
            self.shell,
            fg_color=BG,
            scrollbar_button_color=BLUE,
            scrollbar_button_hover_color=BLUE_DARK,
            corner_radius=0,
        )
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        for name in TAB_NAMES:
            self._tabs[name] = ctk.CTkFrame(self.body, fg_color=BG)

        self._build_ai_tab(self._tabs["Ai"])
        self._build_aim_tab(self._tabs["Aim"])
        self._build_hotkeys_tab(self._tabs["Hotkeys"])
        self._build_detection_tab(self._tabs["Detection window"])

        footer = ctk.CTkFrame(self.shell, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 8))

        self.enabled_var = ctk.BooleanVar(value=self.cfg.enabled)
        enabled = ctk.CTkSwitch(
            footer,
            text="Enabled",
            variable=self.enabled_var,
            command=lambda: setattr(self.cfg, "enabled", self.enabled_var.get()),
            progress_color=BLUE,
            button_color=TEXT,
            text_color=TEXT,
        )
        enabled.pack(side="left", padx=(0, 8))

        self.overlay_var = ctk.BooleanVar(value=self.cfg.show_target_polygon)
        ctk.CTkSwitch(
            footer,
            text="Overlay",
            variable=self.overlay_var,
            command=lambda: setattr(self.cfg, "show_target_polygon", self.overlay_var.get()),
            progress_color=BLUE,
            button_color=TEXT,
            text_color=TEXT,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(footer, text="Save", width=70, command=self._save).pack(side="left", padx=4)
        ctk.CTkButton(footer, text="Load", width=70, command=self._load).pack(side="left", padx=4)

        self.run_btn = ctk.CTkButton(footer, text="Start", width=92, command=self._toggle_run)
        self.run_btn.pack(side="right")

        self.status = ctk.CTkLabel(self.shell, text="Ready", text_color=MUTED, anchor="w")
        self.status.pack(fill="x", padx=18, pady=(0, 8))

    def _build_ai_tab(self, parent: ctk.CTkFrame) -> None:
        self._segmented(parent, "AI Model", "detector_model", _model_options())
        self._slider(
            parent,
            "AI Confidence",
            "detector_conf",
            0.05,
            0.95,
            "{:.2f}",
            "The confidence threshold for AI decisions.",
        )
        self._slider(
            parent,
            "AI Model Image Size",
            "detector_imgsz",
            320,
            1280,
            "{:.0f}",
            "The size of the image fed into the AI model.",
            cast=int,
            to_config=lambda value: int(max(320, min(1280, round(value / 32) * 32))),
        )
        self._slider(
            parent,
            "Capture FPS",
            "capture_fps",
            30,
            240,
            "{:.0f}",
            "Target frame rate for screen capture.",
            cast=int,
        )
        self._segmented(parent, "Mouse backend", "mouse_backend", MOUSE_BACKENDS)
        self._slider(
            parent,
            "Interception mouse index",
            "interception_mouse_index",
            0,
            9,
            "{:.0f}",
            "Device index reported by Interception identify.exe.",
            cast=int,
        )

    def _build_aim_tab(self, parent: ctk.CTkFrame) -> None:
        self._switch(
            parent,
            "Smooth mouse output",
            "smooth_mouse",
            "Selected: ~240 Hz micro-steps (fluid)",
            "Selected: one step per frame (raw)",
        )
        self._slider(
            parent,
            "Speed",
            "speed",
            0,
            5000,
            "{:.0f}",
            "Aiming speed. 5000 means the full remaining distance in one smooth tick.",
            cast=int,
        )
        self._slider(
            parent,
            "Sensitivity",
            "sensitivity",
            0.10,
            10.0,
            "{:.2f}",
            "The value by which mouse coordinates are divided.",
        )
        self._slider(
            parent,
            "FOV width",
            "area_width_pct",
            1,
            100,
            "{:.0f}",
            "The width of the field of view for mouse targeting.",
        )
        self._slider(
            parent,
            "FOV height",
            "area_height_pct",
            1,
            100,
            "{:.0f}",
            "The height of the field of view for mouse targeting.",
        )
        self._slider(
            parent,
            "Random range",
            "jitter",
            0,
            100,
            "{:.0f}",
            "Amplitude of the smooth random aim drift, in pixels.",
            cast=int,
        )
        self._slider(
            parent,
            "Reaction time",
            "reaction_time_ms",
            0,
            400,
            "{:.0f}",
            "Human-like delay (ms) before reacting to a new target. Zero disables.",
            cast=int,
        )
        self._slider(
            parent,
            "Aiming height",
            "head_y_ratio",
            0.05,
            0.50,
            "{:.2f}",
            "Y-axis offset for aiming at the body of the target.",
            on_change=lambda: self._draw_target_preview(),
        )
        self._target_preview(parent)
        self._segmented(parent, "Aim target", "target", TARGET_MODES)
        self._segmented(parent, "Aim mode", "mode", AIM_MODES)
        self._slider(
            parent,
            "Flick threshold",
            "flick_threshold_pct",
            0,
            50,
            "{:.0f}",
            "Distance threshold where Auto switches from smooth to flick.",
        )
        self._slider(
            parent,
            "Aim force",
            "intensity",
            0,
            100,
            "{:.0f}",
            "How strongly the aim closes the remaining distance.",
            cast=int,
        )
        self._slider(
            parent,
            "Max mouse step",
            "max_step_px",
            0,
            500,
            "{:.0f}",
            "Maximum mouse movement per frame. Zero disables the limit.",
        )
        self._slider(
            parent,
            "Target prediction",
            "prediction_ms",
            0,
            60,
            "{:.0f}",
            "Lead the target by this many ms to offset inference lag (box trailing on turns). ~35 is a good start, 0 = off.",
            cast=int,
        )
        self._switch(
            parent,
            "Triggerbot",
            "trigger_enabled",
            "Selected: Auto-fire when on target",
            "Selected: Manual fire",
        )
        self._slider(
            parent,
            "Trigger radius",
            "trigger_radius_px",
            1,
            50,
            "{:.0f}",
            "Auto-fire when the aim point is within this distance (px) from the crosshair.",
        )
        self._slider(
            parent,
            "Trigger delay",
            "trigger_interval_ms",
            50,
            500,
            "{:.0f}",
            "Minimum pause between automatic shots, ms.",
            cast=int,
        )

    def _build_hotkeys_tab(self, parent: ctk.CTkFrame) -> None:
        self._segmented(parent, "Activation mode", "activation", ACTIVATIONS)
        # мышь разрешена только для прицельной клавиши (ПКМ-удержание — норма);
        # exit/pause/reload — только клавиатура, иначе клик ЛКМ в игре дёргал бы их
        self._hotkey_field(parent, "Targeting Hotkey", "activation_key", allow_mouse=True)
        self._hotkey_field(parent, "Exit Hotkey", "exit_hotkey")
        self._hotkey_field(parent, "Pause Hotkey", "pause_hotkey")
        self._hotkey_field(parent, "Reload config hotkey", "reload_config_hotkey")
        ctk.CTkButton(
            parent, text="Reset all hotkeys to default", fg_color=BLUE_DARK,
            command=self._reset_all_hotkeys,
        ).pack(fill="x", pady=(8, 4))

    def _build_detection_tab(self, parent: ctk.CTkFrame) -> None:
        self._slider(
            parent,
            "Detection window height",
            "detection_window_height",
            96,
            1080,
            "{:.0f}",
            "Height of the analysis crop in pixels. Smaller values improve performance.",
            cast=int,
        )
        self._slider(
            parent,
            "Detection window width",
            "detection_window_width",
            128,
            1920,
            "{:.0f}",
            "Width of the analysis crop in pixels. Smaller values improve performance.",
            cast=int,
        )

    def _show_tab(self, name: str) -> None:
        for frame in self._tabs.values():
            frame.pack_forget()
        self._tabs[name].pack(fill="both", expand=True)

    def _row(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=(4, 14))
        return frame

    def _slider(
        self,
        parent: ctk.CTkFrame,
        label: str,
        attr: str,
        lo: float,
        hi: float,
        fmt: str,
        description: str,
        *,
        cast: Callable[[float], object] = float,
        from_config: Callable[[object], float] | None = None,
        to_config: Callable[[float], object] | None = None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        from_config = from_config or (lambda value: float(value))
        to_config = to_config or (lambda value: cast(value))

        frame = self._row(parent)
        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=label, text_color=TEXT, font=("", 14)).pack(side="left")
        value_label = ctk.CTkLabel(
            top,
            text=fmt.format(from_config(getattr(self.cfg, attr))),
            width=52,
            height=24,
            fg_color=PILL,
            text_color=TEXT,
            corner_radius=7,
            font=("", 12, "bold"),
        )
        value_label.pack(side="right")

        def apply_value(raw: float) -> None:
            display_value = int(round(raw)) if cast is int else float(raw)
            setattr(self.cfg, attr, to_config(display_value))
            value_label.configure(text=fmt.format(display_value))
            if on_change:
                on_change()

        slider = ctk.CTkSlider(
            frame,
            from_=lo,
            to=hi,
            command=apply_value,
            button_color=TEXT,
            button_hover_color="#dfe6f6",
            progress_color=TRACK,
            fg_color=TRACK,
        )
        slider.set(from_config(getattr(self.cfg, attr)))
        slider.pack(fill="x", pady=(6, 4))
        ctk.CTkLabel(
            frame,
            text=description,
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=486,
        ).pack(fill="x")
        self._controls[attr] = ("slider", slider, value_label, fmt, from_config, on_change)

    def _segmented(
        self,
        parent: ctk.CTkFrame,
        label: str,
        attr: str,
        mapping: dict[str, object],
    ) -> None:
        frame = self._row(parent)
        ctk.CTkLabel(frame, text=label, text_color=TEXT, font=("", 14)).pack(anchor="w")
        var = ctk.StringVar(value=_label_for(mapping, getattr(self.cfg, attr)))
        control = ctk.CTkSegmentedButton(
            frame,
            values=list(mapping),
            variable=var,
            command=lambda choice: setattr(self.cfg, attr, mapping[choice]),
            fg_color=TAB_BG,
            selected_color=TAB_SELECTED,
            selected_hover_color=TAB_SELECTED,
            unselected_color=TAB_BG,
            unselected_hover_color="#30313a",
            text_color=TEXT,
        )
        control.pack(fill="x", pady=(8, 0))
        self._controls[attr] = ("segmented", var, mapping)

    def _switch(
        self,
        parent: ctk.CTkFrame,
        label: str,
        attr: str,
        on_text: str,
        off_text: str,
    ) -> None:
        frame = self._row(parent)
        var = ctk.BooleanVar(value=bool(getattr(self.cfg, attr)))
        summary = ctk.CTkLabel(frame, text=on_text if var.get() else off_text, text_color=MUTED)

        def apply() -> None:
            setattr(self.cfg, attr, var.get())
            summary.configure(text=on_text if var.get() else off_text)

        ctk.CTkSwitch(
            frame,
            text=label,
            variable=var,
            command=apply,
            progress_color=BLUE,
            button_color=TEXT,
            text_color=TEXT,
            font=("", 14),
        ).pack(anchor="w")
        summary.pack(anchor="w", pady=(6, 0))
        self._controls[attr] = ("switch", var, summary, on_text, off_text)

    def _target_preview(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=(0, 16))
        self.preview_canvas = tk.Canvas(
            frame,
            width=118,
            height=246,
            bg="#031527",
            bd=0,
            highlightthickness=1,
            highlightbackground=BLUE,
        )
        self.preview_canvas.pack(anchor="center")
        self._draw_target_preview()

    def _draw_target_preview(self) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        canvas = self.preview_canvas
        canvas.delete("all")
        w, h = 118, 246
        canvas.create_rectangle(1, 1, w - 2, h - 2, outline=BLUE, fill="#04172a")
        canvas.create_oval(40, 24, 78, 62, fill="#1558b7", outline="#1558b7")
        canvas.create_rectangle(35, 78, 83, 188, fill="#1558b7", outline="#1558b7")
        canvas.create_rectangle(31, 194, 53, 236, fill="#1462d1", outline="#1462d1")
        canvas.create_rectangle(65, 194, 87, 236, fill="#1462d1", outline="#1462d1")
        body_top, body_h = 78, 110
        ratio = max(0.05, min(0.50, float(self.cfg.head_y_ratio)))
        aim_y = body_top + body_h * ratio
        canvas.create_line(0, aim_y, w, aim_y, fill=CYAN, width=3)
        canvas.create_text(
            6,
            aim_y - 10,
            text=f"Head ({ratio:.2f})",
            fill=CYAN,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        )
        canvas.create_text(6, 152, text="Body", fill=CYAN, anchor="w", font=("Segoe UI", 9))
        canvas.create_text(6, 224, text="Legs", fill=CYAN, anchor="w", font=("Segoe UI", 9))

    def _hotkey_field(self, parent: ctk.CTkFrame, label: str, attr: str,
                      allow_mouse: bool = False) -> None:
        self._hotkey_allow_mouse[attr] = allow_mouse
        frame = self._row(parent)
        ctk.CTkLabel(frame, text=label, text_color=TEXT, font=("", 14, "bold")).pack(anchor="w")
        button = ctk.CTkButton(
            frame,
            text=f"Current key: {_pretty_key(getattr(self.cfg, attr))}",
            height=52,
            fg_color=BG,
            hover_color="#101216",
            border_color=TEXT,
            border_width=1,
            corner_radius=7,
            text_color=TEXT,
            anchor="w",
            command=lambda: self._begin_hotkey_capture(attr),
        )
        button.pack(fill="x", pady=(4, 6))
        what = "key or mouse button" if allow_mouse else "keyboard key"
        ctk.CTkLabel(
            frame,
            text=f"Click, then press a {what}.  Esc — cancel,  right-click — reset to default",
            text_color=MUTED,
            anchor="w",
        ).pack(fill="x")
        # ПКМ по полю — сброс этого хоткея на дефолт (на случай если уже «застрял»)
        button.bind("<Button-3>", lambda _e: self._reset_one_hotkey(attr))
        self._controls[attr] = ("hotkey", button)

    def _begin_hotkey_capture(self, attr: str) -> None:
        self._pending_hotkey_attr = attr
        self._hotkey_capture_t = time.monotonic()
        button = self._controls[attr][1]
        allow_mouse = self._hotkey_allow_mouse.get(attr, False)
        button.configure(text="Press a key..." if not allow_mouse else "Press a key or mouse button...")
        self.status.configure(text="Press a key (Esc — cancel)")
        self.focus_force()

    def _cancel_hotkey_capture(self) -> None:
        self._pending_hotkey_attr = None
        self._refresh()  # вернуть кнопке текст "Current key: ..."
        self.status.configure(text="Hotkey change cancelled")

    def _capture_key(self, event: tk.Event) -> None:
        if self._pending_hotkey_attr is None:
            return
        if (event.keysym or "").lower() == "escape":  # Esc всегда отменяет, не назначается
            self._cancel_hotkey_capture()
            return
        key = _key_from_event(event)
        if key:
            self._set_hotkey(self._pending_hotkey_attr, key)

    def _capture_mouse(self, event: tk.Event) -> None:
        attr = self._pending_hotkey_attr
        if attr is None:
            return
        if not self._hotkey_allow_mouse.get(attr, False):
            return  # для этого хоткея кнопки мыши запрещены (ждём клавишу)
        # клик-вход в режим захвата не должен сам стать хоткеем:
        # пропускаем ~400 мс после старта и клик по самому полю хоткея
        if time.monotonic() - self._hotkey_capture_t < 0.4:
            return
        if event.widget is self._controls[attr][1] or getattr(event.widget, "master", None) is self._controls[attr][1]:
            return
        key = _mouse_from_event(event)
        if key:
            self._set_hotkey(attr, key)

    def _reset_one_hotkey(self, attr: str) -> None:
        self._pending_hotkey_attr = None
        setattr(self.cfg, attr, getattr(AimConfig(), attr))
        self._hotkey_edges[attr] = True
        self._refresh()
        self.status.configure(text=f"{attr} reset to {_pretty_key(getattr(self.cfg, attr))}")

    def _reset_all_hotkeys(self) -> None:
        self._pending_hotkey_attr = None
        defaults = AimConfig()
        for attr in ("activation_key", "exit_hotkey", "pause_hotkey", "reload_config_hotkey"):
            setattr(self.cfg, attr, getattr(defaults, attr))
            self._hotkey_edges[attr] = True
        self._refresh()
        self.status.configure(text="All hotkeys reset to default")

    def _set_hotkey(self, attr: str, key: str) -> None:
        setattr(self.cfg, attr, key)
        self._pending_hotkey_attr = None
        # Назначенная клавиша сейчас ещё физически зажата: помечаем её как
        # «уже нажатую», иначе ближайший опрос увидит rising edge и тут же
        # выполнит действие (например, Exit Hotkey закроет приложение).
        self._hotkey_edges[attr] = True
        self._refresh()
        self.status.configure(text=f"{attr} set to {_pretty_key(key)}")

    def _save_preset(self) -> None:
        PRESET.write_text(
            json.dumps(asdict(self.cfg), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def _save(self) -> None:
        self._save_preset()
        self.status.configure(text=f"Saved: {PRESET}")

    def _load(self) -> None:
        if not PRESET.exists():
            self.status.configure(text="Preset file not found")
            return
        loaded = _load_preset_or_default()
        # enabled — runtime-состояние (работа/пауза), а не настройка пресета:
        # загрузка (в т.ч. по hotkey F4) не должна снимать паузу или глушить
        # работающую наводку.
        if self._controller is not None:
            loaded.enabled = self.cfg.enabled
        for field in fields(AimConfig):
            setattr(self.cfg, field.name, getattr(loaded, field.name))
        self._refresh()
        self.status.configure(text=f"Loaded: {PRESET}")

    def _refresh(self) -> None:
        self.enabled_var.set(self.cfg.enabled)
        self.overlay_var.set(self.cfg.show_target_polygon)
        for attr, ref in self._controls.items():
            kind = ref[0]
            value = getattr(self.cfg, attr)
            if kind == "slider":
                _, slider, value_label, fmt, from_config, on_change = ref
                display = from_config(value)
                slider.set(display)
                value_label.configure(text=fmt.format(display))
                if on_change:
                    on_change()
            elif kind == "segmented":
                _, var, mapping = ref
                var.set(_label_for(mapping, value))
            elif kind == "switch":
                _, var, summary, on_text, off_text = ref
                var.set(bool(value))
                summary.configure(text=on_text if var.get() else off_text)
            elif kind == "hotkey":
                _, button = ref
                button.configure(text=f"Current key: {_pretty_key(value)}")

    def _set_enabled(self, enabled: bool) -> None:
        self.cfg.enabled = enabled
        self.enabled_var.set(enabled)

    def _stop_controller(self) -> bool:
        if self._controller is not None:
            self.run_btn.configure(state="disabled")
            self.update_idletasks()
            stopped = self._controller.stop(timeout=20.0)
            self.run_btn.configure(state="normal")
            if not stopped:
                self.status.configure(text="Stop is still in progress")
                return False
            self._controller = None
        return True

    def _toggle_run(self) -> None:
        if self._controller is None:
            from src.aim.controller import AimController

            self._set_enabled(True)
            self._paused_by_button = False
            self._save_preset()
            self._controller = AimController(self.cfg)
            self._controller.start()
            self.run_btn.configure(text="Stop")
            self.status.configure(text="Started. Hold the targeting hotkey to aim.")
            return

        if self._paused_by_button:
            self._set_enabled(True)
            self._paused_by_button = False
            self._save_preset()
            self._controller.start()
            self.run_btn.configure(text="Stop")
            self.status.configure(text="Resumed")
            return

        self._set_enabled(False)
        self._paused_by_button = True
        self.run_btn.configure(text="Start")
        self.status.configure(text="Paused. Capture and Interception stay open.")

    def _poll_hotkeys(self) -> None:
        if self._pending_hotkey_attr is None:
            self._poll_one_hotkey("exit_hotkey", self._on_close)
            self._poll_one_hotkey("pause_hotkey", self._toggle_pause_hotkey)
            self._poll_one_hotkey("reload_config_hotkey", self._load)
        try:
            if self.winfo_exists():
                self.after(120, self._poll_hotkeys)
        except tk.TclError:
            pass

    def _poll_one_hotkey(self, attr: str, action: Callable[[], None]) -> None:
        key = getattr(self.cfg, attr, "")
        # exit/pause/reload не реагируют на кнопки мыши, даже если так записано в
        # конфиге — иначе любой клик ЛКМ/ПКМ в игре дёргал бы их (а reload по ЛКМ
        # ещё и грузил бы испорченный конфиг по кругу).
        if not self._hotkey_allow_mouse.get(attr, False) and str(key).lower().startswith("mouse"):
            return
        is_down = hotkey.is_down(key)
        was_down = self._hotkey_edges.get(attr, False)
        self._hotkey_edges[attr] = is_down
        if is_down and not was_down:
            action()

    def _toggle_pause_hotkey(self) -> None:
        if self._controller is not None:
            self._toggle_run()

    def _poll_overlay(self) -> None:
        state = None
        if self._controller is not None and self.cfg.show_target_polygon:
            state = self._controller.overlay_state
            # контроллер давно не обновлял состояние (умер/завис) — не рисуем устаревшее
            if state is not None and time.monotonic() - state.timestamp > 0.5:
                state = None
        if state is not None:
            if self._overlay is None:
                self._overlay = OverlayWindow(self)
            self._overlay.show(state)
        elif self._overlay is not None:
            self._overlay.hide()
        try:
            if self.winfo_exists():
                self.after(16, self._poll_overlay)  # 60 Гц: меньше визуальный лаг оверлея
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        if self._stop_controller():
            self.destroy()


def main() -> None:
    app = AimbotGUI()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        if app._stop_controller():
            try:
                app.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    main()
