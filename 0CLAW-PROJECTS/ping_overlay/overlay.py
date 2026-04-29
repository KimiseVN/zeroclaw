"""Transparent always-on-top overlay (Tkinter + PIL).

Vẽ glow neon mềm + gradient background bo góc qua PIL, hiển thị qua
tk.Canvas + ImageTk.PhotoImage. Anti-cheat safe: KHÔNG inject, không hook —
chỉ là Win32 window độc lập.

Theme đọc từ config (cyan/magenta cyberpunk mặc định). Kéo overlay bằng
Ctrl+Left-Drag; toạ độ mới được lưu vào config.json qua callback.
"""
from __future__ import annotations

import ctypes
import tkinter as tk
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk


# ---------- Win32 style helpers ----------
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000


def _hide_from_taskbar(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.restype = ctypes.c_long
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style = (style | WS_EX_TOOLWINDOW | WS_EX_LAYERED) & ~WS_EX_APPWINDOW
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


# ---------- Color helpers ----------
def _hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = (s or "#FFFFFF").lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return 255, 255, 255


def _lerp_color(a: tuple[int, int, int], b: tuple[int, int, int],
                t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


# ---------- Font resolver ----------
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Tahoma Bold > Segoe UI Bold > Arial Bold > default. Tránh fail trên
    máy thiếu font (PIL load_default rất xấu nhưng chạy được)."""
    candidates = [
        "tahomabd.ttf", "segoeuib.ttf", "arialbd.ttf",
        "tahoma.ttf", "segoeui.ttf", "arial.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()  # type: ignore[return-value]


# ---------- Theme container ----------
class _Theme:
    def __init__(self, theme_cfg: dict | None, overlay_cfg: dict | None):
        t = theme_cfg or {}
        o = overlay_cfg or {}
        self.text_rgb = _hex_to_rgb(t.get("text", "#00E5FF"))
        self.glow_rgb = _hex_to_rgb(t.get("glow", "#FF00AA"))
        self.bg_left_rgb = _hex_to_rgb(t.get("bg_left", "#0A2A3A"))
        self.bg_right_rgb = _hex_to_rgb(t.get("bg_right", "#3A0A2A"))
        self.font_size = int(o.get("font_size", 14))
        self.padding = int(o.get("padding", 12))
        self.corner_radius = int(o.get("corner_radius", 12))
        self.glow_radius = int(o.get("glow_radius", 5))
        self.bg_alpha = max(0, min(255, int(o.get("bg_alpha", 170))))
        self.window_alpha = float(o.get("window_alpha", 0.92))


# ---------- Renderer ----------
class _GlowRenderer:
    """Cache font + tái sử dụng object PIL nơi có thể."""

    def __init__(self, theme: _Theme):
        self.theme = theme
        self.font = _load_font(theme.font_size)

    def update_theme(self, theme: _Theme) -> None:
        # Reload font nếu size đổi
        if theme.font_size != self.theme.font_size:
            self.font = _load_font(theme.font_size)
        self.theme = theme

    def _gradient(self, w: int, h: int) -> Image.Image:
        """Linear gradient ngang. Build 1-pixel row rồi resize NEAREST -
        nhanh hơn nhiều so với double-loop set_pixel.
        """
        row = Image.new("RGB", (max(1, w), 1))
        px = row.load()
        left = self.theme.bg_left_rgb
        right = self.theme.bg_right_rgb
        for x in range(w):
            t = x / max(1, w - 1)
            px[x, 0] = _lerp_color(left, right, t)
        return row.resize((w, h), Image.NEAREST).convert("RGBA")

    def render(self, text: str) -> Image.Image:
        """Trả RGB image, đã flatten lên nền đen (transparentcolor)."""
        T = self.theme
        # 1. Đo text
        tmp = Image.new("RGBA", (1, 1))
        d = ImageDraw.Draw(tmp)
        bbox = d.textbbox((0, 0), text, font=self.font)
        tw = max(1, bbox[2] - bbox[0])
        th = max(1, bbox[3] - bbox[1])
        # Để chừa khoảng cho glow halo lan ra ngoài bbox
        glow_pad = T.glow_radius * 2 + 2
        W = tw + T.padding * 2 + glow_pad * 2
        H = th + T.padding + glow_pad * 2

        # 2. Glow layer (text màu glow, blur)
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        text_x = T.padding + glow_pad - bbox[0]
        text_y = T.padding // 2 + glow_pad - bbox[1]
        gd.text((text_x, text_y), text,
                fill=T.glow_rgb + (255,), font=self.font)
        glow = glow.filter(ImageFilter.GaussianBlur(radius=T.glow_radius))

        # 3. Background gradient với mask rounded rect
        bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        grad = self._gradient(W, H)
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle(
            (glow_pad // 2, glow_pad // 2,
             W - glow_pad // 2 - 1, H - glow_pad // 2 - 1),
            radius=T.corner_radius, fill=T.bg_alpha,
        )
        bg.paste(grad, (0, 0), mask)

        # 4. Composite: bg + glow + sharp text
        comp = Image.alpha_composite(bg, glow)
        sharp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sharp)
        sd.text((text_x, text_y), text,
                fill=T.text_rgb + (255,), font=self.font)
        final = Image.alpha_composite(comp, sharp)

        # 5. Flatten lên nền đen — cần cho transparentcolor='black'
        flat = Image.new("RGB", (W, H), (0, 0, 0))
        flat.paste(final, (0, 0), final.split()[3])
        return flat


# ---------- Overlay window ----------
class Overlay:
    """Compact overlay: Canvas + ImageTk; bám client area của game; Ctrl+drag
    để di chuyển; offset lưu config qua `on_offset_changed` callback.
    """

    def __init__(self, cfg: dict | None = None,
                 on_offset_changed: Callable[[int, int], None] | None = None):
        cfg = cfg or {}
        self._theme = _Theme(cfg.get("theme"), cfg.get("overlay"))
        self._renderer = _GlowRenderer(self._theme)
        self._on_offset_changed = on_offset_changed

        ov = cfg.get("overlay") or {}
        self._offset = (int(ov.get("offset_x", 12)),
                        int(ov.get("offset_y", 8)))
        self._last_client_xy: tuple[int, int] | None = None
        self._drag: dict | None = None

        self.root = tk.Tk()
        self.root.title("PingOverlay")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self._theme.window_alpha)
        self.root.attributes("-transparentcolor", "black")
        self.root.configure(bg="black")

        self.canvas = tk.Canvas(
            self.root, width=200, height=40,
            bg="black", highlightthickness=0, bd=0, takefocus=0,
        )
        self.canvas.pack()
        self._photo: ImageTk.PhotoImage | None = None
        self._img_item = self.canvas.create_image(0, 0, anchor="nw")
        self._last_render_key: tuple[str, tuple[int, int, int], int] | None = None
        self._last_window_size: tuple[int, int] | None = None
        self._last_window_pos: tuple[int, int] | None = None

        # Fallback vị trí khi chưa có client area của game
        self.root.geometry(f"+{30}+{30}")

        # Hide khỏi taskbar sau khi window đã map
        self.root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        _hide_from_taskbar(hwnd)
        self.root.withdraw()
        self.root.after(10, self.root.deiconify)

        # Bindings: Ctrl+drag để move, click thuần KHÔNG làm gì (giữ cho
        # tray double-click toggle). ButtonRelease-1 luôn xử lý để kết
        # thúc drag dù user buông Ctrl trước.
        self.canvas.bind("<Control-ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<Control-B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

        self._visible = True
        self.set_text("Khởi tạo...")

    # --- public API ---
    def set_text(self, text: str, color: str | None = None) -> None:
        """Render text (PIL glow + gradient). `color` để tương thích API
        cũ — nếu set, override màu text 1 lần. Không persist."""
        text = text or " "
        if color is not None:
            try:
                new_rgb = _hex_to_rgb(color)
                if new_rgb != self._theme.text_rgb:
                    self._theme.text_rgb = new_rgb
                    self._renderer.update_theme(self._theme)
                    self._last_render_key = None
            except Exception:
                pass
        render_key = (text, self._theme.text_rgb, self._theme.font_size)
        if render_key == self._last_render_key:
            return
        try:
            img = self._renderer.render(text)
        except Exception as e:
            # Fallback cực ngắn: đặt rỗng để không treo
            print(f"[overlay] render error: {e}")
            return
        self._photo = ImageTk.PhotoImage(img)
        self._last_render_key = render_key
        self.canvas.configure(width=img.width, height=img.height)
        self.canvas.itemconfigure(self._img_item, image=self._photo)
        # Giữ size window đồng bộ (nếu width đổi). Tk geometry: "WxH+X+Y".
        try:
            geom = self.root.geometry()
            if "x" in geom and "+" in geom:
                _size, pos = geom.split("+", 1)  # "WxH", "X+Y"
                size = (img.width, img.height)
                if size != self._last_window_size:
                    self.root.geometry(f"{img.width}x{img.height}+{pos}")
                    self._last_window_size = size
        except Exception:
            pass

    def set_theme(self, theme_cfg: dict | None,
                  overlay_cfg: dict | None) -> None:
        self._theme = _Theme(theme_cfg, overlay_cfg)
        self._renderer.update_theme(self._theme)
        self._last_render_key = None
        try:
            self.root.attributes("-alpha", self._theme.window_alpha)
        except Exception:
            pass

    def set_offset(self, x: int, y: int) -> None:
        self._offset = (int(x), int(y))

    def move_to_client(self, x: int, y: int) -> None:
        """Đặt overlay sát góc trên-trái client area của cửa sổ game."""
        if self._drag is not None:
            return  # đang user kéo, không cướp vị trí
        self._last_client_xy = (int(x), int(y))
        try:
            ox, oy = self._offset
            target = (x + ox, y + oy)
            if target == self._last_window_pos:
                return
            self.root.geometry(f"+{target[0]}+{target[1]}")
            self._last_window_pos = target
            self.root.attributes("-topmost", True)
        except Exception:
            pass

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def hide(self) -> None:
        if not self._visible:
            return
        self.root.withdraw()
        self._visible = False

    def show(self) -> None:
        if self._visible:
            return
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self._visible = True

    def is_visible(self) -> bool:
        return self._visible

    def close(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass

    def schedule(self, ms: int, fn) -> None:
        self.root.after(ms, fn)

    def mainloop(self) -> None:
        self.root.mainloop()

    # --- drag handlers ---
    def _current_xy(self) -> tuple[int, int]:
        try:
            self.root.update_idletasks()
            return int(self.root.winfo_x()), int(self.root.winfo_y())
        except Exception:
            return 0, 0

    def _on_drag_start(self, e) -> None:
        self._drag = {
            "start_root": (e.x_root, e.y_root),
            "start_geom": self._current_xy(),
        }

    def _on_drag_motion(self, e) -> None:
        if not self._drag:
            return
        dx = e.x_root - self._drag["start_root"][0]
        dy = e.y_root - self._drag["start_root"][1]
        nx = self._drag["start_geom"][0] + dx
        ny = self._drag["start_geom"][1] + dy
        try:
            self.root.geometry(f"+{nx}+{ny}")
        except Exception:
            pass

    def _on_drag_end(self, e) -> None:
        if not self._drag:
            return
        self._drag = None
        if self._last_client_xy is None:
            return
        wx, wy = self._current_xy()
        cx, cy = self._last_client_xy
        new_off = (wx - cx, wy - cy)
        self._offset = new_off
        if self._on_offset_changed:
            try:
                self._on_offset_changed(new_off[0], new_off[1])
            except Exception as e2:
                print(f"[overlay] offset persist failed: {e2}")

    def _on_enter(self, _e) -> None:
        # Hint UI khi hover: tăng alpha nhẹ để Kim biết có thể kéo
        try:
            self.root.attributes("-alpha",
                                 min(1.0, self._theme.window_alpha + 0.05))
        except Exception:
            pass

    def _on_leave(self, _e) -> None:
        try:
            self.root.attributes("-alpha", self._theme.window_alpha)
        except Exception:
            pass
