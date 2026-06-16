"""Прозрачный click-through оверлей поверх игры: рисует то, что видит аимбот.

Окно topmost без рамки; фон выбит цветом-ключом (-transparentcolor), мышь
проходит насквозь (WS_EX_TRANSPARENT). Ключевое: окно исключено из захвата
экрана (SetWindowDisplayAffinity WDA_EXCLUDEFROMCAPTURE, Windows 10 2004+),
поэтому собственные рамки НЕ попадают в кадры детектора и не влияют на YOLO.

Ограничение: рисуется поверх игры в windowed/borderless; поверх exclusive
fullscreen оверлей не виден.
"""

import ctypes
import tkinter as tk

from src.aim.overlay import OverlayState

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
GA_ROOT = 2
WDA_EXCLUDEFROMCAPTURE = 0x00000011

TRANSPARENT_KEY = "#000001"  # цвет-ключ: всё, что им закрашено, прозрачно
ENEMY_COLOR = "#ff5050"
HEAD_COLOR = "#ffd24a"
TEAMMATE_COLOR = "#39d465"
TARGET_COLOR = "#00e5ff"
ZONE_COLOR = "#3a7bd5"


class OverlayWindow:
    """Рисует OverlayState. Управляется из GUI-потока (show/hide/destroy)."""

    def __init__(self, master: tk.Misc):
        self._win = tk.Toplevel(master)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-transparentcolor", TRANSPARENT_KEY)
        self._win.configure(bg=TRANSPARENT_KEY)
        self._canvas = tk.Canvas(self._win, bg=TRANSPARENT_KEY, highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)
        self._region: tuple[int, int, int, int] | None = None
        self._visible = False
        self._affinity_warned = False
        self._win.withdraw()

    def _apply_window_styles(self) -> None:
        """Click-through, без Alt-Tab/фокуса, невидим для захвата экрана."""
        try:
            self._win.update_idletasks()
            user32 = ctypes.windll.user32
            hwnd = user32.GetAncestor(self._win.winfo_id(), GA_ROOT)
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                style | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            )
            if not user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
                if not self._affinity_warned:
                    self._affinity_warned = True
                    print(
                        "[overlay] не удалось исключить оверлей из захвата экрана — "
                        "рамки будут видны детектору (Windows старее 10 2004?)"
                    )
        except Exception as exc:
            print(f"[overlay] стили окна не применились: {exc}")

    def show(self, state: OverlayState) -> None:
        left, top, width, height = state.region
        if width <= 0 or height <= 0:  # нечего показывать (пустой регион)
            self.hide()
            return
        if self._region != state.region:
            self._win.geometry(f"{width}x{height}+{left}+{top}")
            self._region = state.region
        if not self._visible:
            self._win.deiconify()
            self._win.lift()
            self._win.attributes("-topmost", True)
            # после deiconify Tk может пересоздать нативное окно — применяем заново
            self._apply_window_styles()
            self._visible = True
            print(f"[overlay] окно показано: {width}x{height} @ ({left},{top})")
        self._draw(state)

    def hide(self) -> None:
        if self._visible:
            self._canvas.delete("all")
            self._win.withdraw()
            self._visible = False

    def destroy(self) -> None:
        try:
            self._win.destroy()
        except tk.TclError:
            pass

    def _draw(self, state: OverlayState) -> None:
        canvas = self._canvas
        canvas.delete("all")
        zx1, zy1, zx2, zy2 = state.zone
        canvas.create_rectangle(zx1, zy1, zx2, zy2, outline=ZONE_COLOR, dash=(4, 4))
        for x1, y1, x2, y2 in state.teammates:
            canvas.create_rectangle(x1, y1, x2, y2, outline=TEAMMATE_COLOR, width=2)
        for x1, y1, x2, y2 in state.enemies:
            canvas.create_rectangle(x1, y1, x2, y2, outline=ENEMY_COLOR, width=2)
        for x1, y1, x2, y2 in state.heads:
            canvas.create_rectangle(x1, y1, x2, y2, outline=HEAD_COLOR)
        if state.target_box is not None:
            x1, y1, x2, y2 = state.target_box
            canvas.create_rectangle(x1, y1, x2, y2, outline=TARGET_COLOR, width=3)
        if state.aim_point is not None:
            px, py = state.aim_point
            canvas.create_oval(px - 3, py - 3, px + 3, py + 3, outline=TARGET_COLOR, fill=TARGET_COLOR)
        # latency/FPS в левом верхнем углу кадра
        if state.inference_ms or state.fps:
            canvas.create_text(
                8, 8, anchor="nw", fill=TARGET_COLOR, font=("Consolas", 11, "bold"),
                text=f"inf {state.inference_ms:.0f} ms | {state.fps:.0f} FPS",
            )
