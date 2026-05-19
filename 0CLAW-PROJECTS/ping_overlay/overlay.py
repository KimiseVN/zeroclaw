"""Transparent always-on-top overlay (Tkinter + PIL).

Vẽ glow neon mềm + gradient background bo góc qua PIL, hiển thị qua
tk.Canvas + ImageTk.PhotoImage. Anti-cheat safe: KHÔNG inject, không hook —
chỉ là Win32 window độc lập.

Theme đọc từ config (cyan/magenta cyberpunk mặc định). Kéo overlay bằng
Ctrl+Left-Drag; toạ độ mới được lưu vào config.json qua callback.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
import tkinter as tk
import unicodedata
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

from ui_runtime import apply_custom_cursor


# ---------- Win32 style helpers ----------
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
GA_ROOT = 2
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def _hide_from_taskbar(hwnd: int) -> None:
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    style = user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
    style = (style | WS_EX_TOOLWINDOW | WS_EX_LAYERED) & ~WS_EX_APPWINDOW
    user32.SetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE, style)


def _virtual_screen_bounds() -> tuple[int, int, int, int]:
    user32 = ctypes.windll.user32
    left = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
    top = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    width = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    height = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    if width <= 0 or height <= 0:
        return 0, 0, int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    return left, top, left + width, top + height


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
    """Segoe UI (Windows default) → Tahoma → Arial fallback chain."""
    candidates = [
        "segoeui.ttf", "SegUIVar.ttf",
        "tahoma.ttf", "arial.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()  # type: ignore[return-value]


def _load_bold_font(size: int) -> tuple[ImageFont.FreeTypeFont, bool]:
    """Returns (bold_font, is_simulated).

    is_simulated=True → no real bold variant found; draw code must overlay
    a +1px x-shifted copy to fake bold weight.
    is_simulated=False → real bold face loaded; no simulation needed.
    """
    candidates = [
        "segoeuib.ttf", "SegUIVar.ttf",
        "tahomabd.ttf", "arialbd.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size), False
        except Exception:
            continue
    return _load_font(size), True   # fallback → simulate via +1px shift


def _load_named_fonts(size: int, names: list[str]) -> list[ImageFont.FreeTypeFont]:
    fonts: list[ImageFont.FreeTypeFont] = []
    for name in names:
        try:
            fonts.append(ImageFont.truetype(name, size))
        except Exception:
            continue
    return fonts


def _is_emoji_or_symbol(ch: str) -> bool:
    code = ord(ch)
    if code in (0xFE0E, 0xFE0F, 0x200D):
        return True
    if 0x1F000 <= code <= 0x1FAFF:
        return True
    if 0x2600 <= code <= 0x27BF:
        return True
    return unicodedata.category(ch).startswith("S")


def _is_format_selector(ch: str) -> bool:
    return ord(ch) in (0xFE0E, 0xFE0F, 0x200D)


# ---------- Theme container ----------
def _strip_fringe(img: Image.Image, threshold: int = 40) -> Image.Image:
    """Xóa pixel viền tối tạo ra bởi LANCZOS downscale trên nền đen.

    Khi transparent overlay dùng SSAA (2× → 1×), LANCZOS tạo pixel biên
    trung gian giữa màu text và đen. Các pixel này không phải (0,0,0) thuần
    nên Tk transparentcolor không xóa được → thành viền quanh chữ.

    Giải pháp: pixel nào có luminance ≤ threshold → ép về (0,0,0) để
    transparentcolor loại bỏ. Chỉ gọi ở transparent path.

    threshold=40 ≈ 16% của 255 — thấp hơn bất kỳ pixel text nào có
    luminance đáng kể, nhưng cao hơn fringe LANCZOS điển hình (~10-25%).
    """
    gray = img.convert("L")
    keep = gray.point(lambda v: 255 if v > threshold else 0)
    return Image.composite(img, Image.new("RGB", img.size, (0, 0, 0)), keep)


class _Theme:
    def __init__(self, theme_cfg: dict | None, overlay_cfg: dict | None):
        t = theme_cfg or {}
        o = overlay_cfg or {}
        try:
            self.scale = float(o.get("scale", 1.0))
        except (TypeError, ValueError):
            self.scale = 1.0
        self.scale = max(0.7, min(1.8, self.scale))
        self.transparent_background = bool(o.get("transparent_background", False))
        self.text_rgb = _hex_to_rgb(t.get("text", "#00E5FF"))
        self.glow_rgb = _hex_to_rgb(t.get("glow", "#FF00AA"))
        self.bg_left_rgb = _hex_to_rgb(t.get("bg_left", "#0A2A3A"))
        self.bg_right_rgb = _hex_to_rgb(t.get("bg_right", "#3A0A2A"))
        self.font_size = max(8, int(round(int(o.get("font_size", 14)) * self.scale)))
        self.padding = max(4, int(round(int(o.get("padding", 12)) * self.scale)))
        self.corner_radius = max(4, int(round(int(o.get("corner_radius", 12)) * self.scale)))
        self.glow_radius = max(0, int(round(int(o.get("glow_radius", 5)) * self.scale)))
        self.bg_alpha = max(0, min(255, int(o.get("bg_alpha", 170))))
        self.window_alpha = float(o.get("window_alpha", 0.92))

    def render_key(self) -> tuple:
        return (
            self.text_rgb,
            self.glow_rgb,
            self.bg_left_rgb,
            self.bg_right_rgb,
            self.font_size,
            self.padding,
            self.corner_radius,
            self.glow_radius,
            self.bg_alpha,
            self.transparent_background,
        )


# ---------- Renderer ----------
class _GlowRenderer:
    """Cache font + tái sử dụng object PIL nơi có thể."""

    # SSAA supersampling factor: render nội bộ ở _S× rồi LANCZOS downscale
    # → font mịn tự nhiên, không răng cưa, không cần sub-pixel ClearType.
    _S: int = 2

    def __init__(self, theme: _Theme):
        self.theme = theme
        _fb_names = [
            "seguisym.ttf", "seguiemj.ttf",
            "Segoe UI Symbol.ttf", "Segoe UI Emoji.ttf",
            "symbol.ttf", "segoeui.ttf", "arialuni.ttf",
        ]
        _bfb_names = [
            "seguisym.ttf", "seguiemj.ttf",
            "Segoe UI Symbol.ttf", "Segoe UI Emoji.ttf",
            "symbol.ttf", "segoeuib.ttf", "arialbd.ttf",
        ]
        # 1× fonts — dùng để đo layout (bbox), KHÔNG dùng để vẽ
        self.font = _load_font(theme.font_size)
        self.bold_font, self._bold_simulated = _load_bold_font(theme.font_size)
        self.fallback_fonts = _load_named_fonts(theme.font_size, _fb_names)
        self.bold_fallback_fonts = _load_named_fonts(theme.font_size, _bfb_names)
        # S× hi-res fonts — dùng để vẽ SSAA, sau đó downscale
        self._font_s = _load_font(theme.font_size * self._S)
        self._bold_font_s, _ = _load_bold_font(theme.font_size * self._S)
        self._fallback_fonts_s = _load_named_fonts(theme.font_size * self._S, _fb_names)
        self._bold_fallback_fonts_s = _load_named_fonts(theme.font_size * self._S, _bfb_names)

    def update_theme(self, theme: _Theme) -> None:
        if theme.font_size != self.theme.font_size:
            _fb_names = [
                "seguisym.ttf", "seguiemj.ttf",
                "Segoe UI Symbol.ttf", "Segoe UI Emoji.ttf",
                "symbol.ttf", "segoeui.ttf", "arialuni.ttf",
            ]
            _bfb_names = [
                "seguisym.ttf", "seguiemj.ttf",
                "Segoe UI Symbol.ttf", "Segoe UI Emoji.ttf",
                "symbol.ttf", "segoeuib.ttf", "arialbd.ttf",
            ]
            self.font = _load_font(theme.font_size)
            self.bold_font, self._bold_simulated = _load_bold_font(theme.font_size)
            self.fallback_fonts = _load_named_fonts(theme.font_size, _fb_names)
            self.bold_fallback_fonts = _load_named_fonts(theme.font_size, _bfb_names)
            self._font_s = _load_font(theme.font_size * self._S)
            self._bold_font_s, _ = _load_bold_font(theme.font_size * self._S)
            self._fallback_fonts_s = _load_named_fonts(theme.font_size * self._S, _fb_names)
            self._bold_fallback_fonts_s = _load_named_fonts(theme.font_size * self._S, _bfb_names)
        self.theme = theme

    def _font_for_char(self, ch: str, *, bold: bool = False, hi: bool = False) -> ImageFont.ImageFont | None:
        if _is_format_selector(ch):
            return None
        if hi:
            base = self._bold_font_s if bold else self._font_s
            fb   = self._bold_fallback_fonts_s if bold else self._fallback_fonts_s
        else:
            base = self.bold_font if bold else self.font
            fb   = self.bold_fallback_fonts if bold else self.fallback_fonts
        if _is_emoji_or_symbol(ch):
            return fb[0] if fb else base
        return base

    def _text_bbox(self, draw: ImageDraw.ImageDraw, text: str, *, bold: bool = False) -> tuple[int, int, int, int]:
        x = 0
        left = 0
        top = 0
        right = 0
        bottom = 0
        seen = False
        for ch in text:
            font = self._font_for_char(ch, bold=bold)
            if font is None:
                continue
            bbox = draw.textbbox((0, 0), ch, font=font)
            width = max(0, bbox[2] - bbox[0])
            if not seen:
                left = x + bbox[0]
                top = bbox[1]
                right = x + bbox[2]
                bottom = bbox[3]
                seen = True
            else:
                left = min(left, x + bbox[0])
                top = min(top, bbox[1])
                right = max(right, x + bbox[2])
                bottom = max(bottom, bbox[3])
            x += width
        if not seen:
            return (0, 0, 1, 1)
        if bold and self._bold_simulated:
            right += 1  # extra pixel for bold +1px offset simulation (no real bold face)
        return (left, top, right, bottom)

    def _draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        xy: tuple[float, float],
        text: str,
        fill: tuple[int, int, int, int],
        *,
        bold: bool = False,
        hi: bool = False,
    ) -> None:
        x, y = xy
        # bold_offset > 0 only when simulating bold via +1px shift (no real bold face)
        bold_offset = (self._S if hi else 1) if self._bold_simulated else 0
        for ch in text:
            font = self._font_for_char(ch, bold=bold, hi=hi)
            if font is None:
                continue
            draw.text((x, y), ch, fill=fill, font=font)
            if bold and bold_offset:
                # Simulate bold: overlay a shifted copy (scales with SSAA factor)
                draw.text((x + bold_offset, y), ch, fill=fill, font=font)
            bbox = draw.textbbox((0, 0), ch, font=font)
            x += max(0, bbox[2] - bbox[0])

    def _draw_keyed_text(
        self,
        image: Image.Image,
        xy: tuple[float, float],
        text: str,
        fill: tuple[int, int, int],
        *,
        bold: bool = False,
        hi: bool = False,
    ) -> None:
        """Draw text onto the RGB transparent-color surface without
        semi-transparent fringe pixels.

        Tk/Win32 transparent color only removes exact black pixels.
        Normal anti-aliased RGBA text leaves dark blended edge pixels
        after flattening, which look like a black halo. This mask is
        intentionally thresholded so transparent overlay mode shows
        only clean glyph pixels.
        """
        if image.mode != "RGB":
            return
        mask = Image.new("L", image.size, 0)
        md = ImageDraw.Draw(mask)
        x, y = xy
        bold_offset = (self._S if hi else 1) if self._bold_simulated else 0
        for ch in text:
            font = self._font_for_char(ch, bold=bold, hi=hi)
            if font is None:
                continue
            md.text((int(round(x)), int(round(y))), ch, fill=255, font=font)
            if bold and bold_offset:
                md.text((int(round(x)) + bold_offset, int(round(y))), ch, fill=255, font=font)
            bbox = md.textbbox((0, 0), ch, font=font)
            x += max(0, bbox[2] - bbox[0])
        hard_mask = mask.point(lambda a: 255 if a >= 96 else 0)
        image.paste(Image.new("RGB", image.size, fill), (0, 0), hard_mask)

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
        """Render text → RGB image (SSAA _S× rồi LANCZOS downscale → font mịn)."""
        T = self.theme
        S = self._S

        # 1. Đo layout ở 1× để xác định kích thước output cuối
        tmp = Image.new("RGBA", (1, 1))
        d = ImageDraw.Draw(tmp)
        bbox = self._text_bbox(d, text)
        tw = max(1, bbox[2] - bbox[0])
        th = max(1, bbox[3] - bbox[1])
        glow_pad = T.glow_radius * 2 + 2
        W = tw + T.padding * 2 + glow_pad * 2   # output width  (1×)
        H = th + T.padding + glow_pad * 2        # output height (1×)

        # 2. Hi-res canvas (S×) cho SSAA
        Ws, Hs = W * S, H * S
        tx_s = (T.padding + glow_pad - bbox[0]) * S   # draw origin X
        ty_s = (T.padding // 2 + glow_pad - bbox[1]) * S  # draw origin Y
        gp_s = glow_pad * S

        if T.transparent_background:
            flat_s = Image.new("RGB", (Ws, Hs), (0, 0, 0))
            self._draw_keyed_text(flat_s, (tx_s, ty_s), text, T.text_rgb, hi=True)
            # Strip LANCZOS fringe: dark edge pixels → pure black → transparentcolor removes them
            return _strip_fringe(flat_s.resize((W, H), Image.LANCZOS))

        # Glow layer — dùng cùng màu text (không phải T.glow_rgb) ở opacity thấp
        # để tạo halo mềm cùng màu thay vì viền tương phản màu.
        glow_s = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_s)
        self._draw_text(gd, (tx_s, ty_s), text, T.text_rgb + (160,), hi=True)
        glow_s = glow_s.filter(ImageFilter.GaussianBlur(radius=T.glow_radius * S))

        # Background gradient với rounded rect mask
        bg_s = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
        grad_s = self._gradient(Ws, Hs)
        bmask_s = Image.new("L", (Ws, Hs), 0)
        bmd = ImageDraw.Draw(bmask_s)
        bmd.rounded_rectangle(
            (gp_s // 2, gp_s // 2, Ws - gp_s // 2 - 1, Hs - gp_s // 2 - 1),
            radius=T.corner_radius * S, fill=T.bg_alpha,
        )
        bg_s.paste(grad_s, (0, 0), bmask_s)

        # Sharp text layer
        sharp_s = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sharp_s)
        self._draw_text(sd, (tx_s, ty_s), text, T.text_rgb + (255,), hi=True)

        # Composite + flatten lên nền đen
        comp = Image.alpha_composite(bg_s, glow_s)
        final_s = Image.alpha_composite(comp, sharp_s)
        flat_s = Image.new("RGB", (Ws, Hs), (0, 0, 0))
        flat_s.paste(final_s, (0, 0), final_s.split()[3])

        # 3. Downscale → kết quả mịn (LANCZOS anti-aliasing)
        return flat_s.resize((W, H), Image.LANCZOS)

    def render_segments(self, segments: list[dict[str, Any]], default_color: str | None = None) -> Image.Image:
        """Render normal metric segments plus optional highlighted event pills."""
        T = self.theme
        metric_rgb = _hex_to_rgb(default_color) if default_color else T.text_rgb
        sep = "  │  "
        tmp = Image.new("RGBA", (1, 1))
        d = ImageDraw.Draw(tmp)

        items: list[dict[str, Any]] = []
        sep_bbox = self._text_bbox(d, sep)
        sep_w = max(1, sep_bbox[2] - sep_bbox[0])
        sep_h = max(1, sep_bbox[3] - sep_bbox[1])
        total_w = 0
        max_h = sep_h
        for idx, raw in enumerate(segments):
            text = str(raw.get("text") or "")
            if not text:
                continue
            kind = str(raw.get("kind") or "metric")

            # Pre-compute label/value split for metric items (e.g. "Ping: 30ms")
            # Label part uses normal font weight; value part uses bold (simulated).
            has_split = kind == "metric" and ": " in text
            label_part: str = ""
            value_part: str = text
            label_bbox_s: tuple[int, int, int, int] = (0, 0, 0, 0)
            value_bbox_s: tuple[int, int, int, int] = (0, 0, 0, 0)
            label_w_s: int = 0

            if has_split:
                sep_idx = text.index(": ") + 2
                label_part = text[:sep_idx]   # e.g. "Ping: "
                value_part = text[sep_idx:]   # e.g. "30ms"
                lb = self._text_bbox(d, label_part, bold=False)
                vb = self._text_bbox(d, value_part, bold=True)
                label_w_s = max(0, lb[2] - lb[0])
                value_w_s = max(0, vb[2] - vb[0])
                bbox = (
                    lb[0],
                    min(lb[1], vb[1]),
                    lb[0] + label_w_s + value_w_s,
                    max(lb[3], vb[3]),
                )
                tw = label_w_s + value_w_s
                th = max(1, bbox[3] - bbox[1])
                label_bbox_s = lb
                value_bbox_s = vb
            else:
                bbox = self._text_bbox(d, text, bold=(kind == "event"))
                tw = max(1, bbox[2] - bbox[0])
                th = max(1, bbox[3] - bbox[1])

            min_text = str(raw.get("min_text") or "")
            min_w = 0
            if min_text:
                min_bbox = self._text_bbox(d, min_text, bold=(kind == "event"))
                min_w = max(1, min_bbox[2] - min_bbox[0])
            pill_pad_x = 10 if kind == "event" else 0
            pill_pad_y = 4 if kind == "event" else 0
            w = max(tw, min_w) + pill_pad_x * 2
            h = th + pill_pad_y * 2
            if items:
                total_w += sep_w
            total_w += w
            max_h = max(max_h, h)
            items.append({
                "text": text,
                "kind": kind,
                "bbox": bbox,
                "tw": tw,
                "th": th,
                "w": w,
                "content_w": max(tw, min_w),
                "h": h,
                "pill_pad_x": pill_pad_x,
                "pill_pad_y": pill_pad_y,
                "color": raw.get("color"),
                "has_split": has_split,
                "label_part": label_part,
                "value_part": value_part,
                "label_w": label_w_s,
                "label_bbox": label_bbox_s,
                "value_bbox": value_bbox_s,
            })

        if not items:
            return self.render(" ")

        glow_pad = T.glow_radius * 2 + 2
        W = total_w + T.padding * 2 + glow_pad * 2   # output width  (1×)
        H = max_h + T.padding + glow_pad * 2          # output height (1×)
        text_x = T.padding + glow_pad                 # 1× cursor start
        center_y = H // 2

        # SSAA: vẽ trên canvas S× rồi LANCZOS downscale → font mịn
        S = self._S
        Ws, Hs = W * S, H * S
        gp_s = glow_pad * S
        cy_s = center_y * S
        sep_rgb = (150, 180, 190)

        # sep đo ở 1× → scale lên S× để dùng trong drawing loop
        sep_bbox_s = tuple(v * S for v in sep_bbox)
        sep_w_s = max(1, sep_bbox_s[2] - sep_bbox_s[0])
        sep_h_s = max(1, sep_bbox_s[3] - sep_bbox_s[1])

        bg_s = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
        if not T.transparent_background:
            grad_s = self._gradient(Ws, Hs)
            bmask_s = Image.new("L", (Ws, Hs), 0)
            bmd = ImageDraw.Draw(bmask_s)
            bmd.rounded_rectangle(
                (gp_s // 2, gp_s // 2, Ws - gp_s // 2 - 1, Hs - gp_s // 2 - 1),
                radius=T.corner_radius * S,
                fill=T.bg_alpha,
            )
            bg_s.paste(grad_s, (0, 0), bmask_s)

        glow_s = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
        sharp_s = Image.new("RGBA", (Ws, Hs), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_s)
        sd = ImageDraw.Draw(sharp_s)
        x_s = text_x * S   # hi-res draw cursor
        keyed_text: list[tuple[float, float, str, tuple[int, int, int], bool]] = []

        for idx, item in enumerate(items):
            if idx:
                sep_y_s = cy_s - sep_h_s // 2 - sep_bbox_s[1]
                if T.transparent_background:
                    keyed_text.append((x_s, sep_y_s, sep, sep_rgb, False))
                else:
                    self._draw_text(sd, (x_s, sep_y_s), sep, sep_rgb + (180,), hi=True)
                x_s += sep_w_s

            kind = item["kind"]
            bbox = item["bbox"]           # 1× bbox
            seg_h_s = item["h"] * S
            y_box_s = cy_s - seg_h_s // 2

            if kind == "event":
                w_s = item["w"] * S
                rect_s = (x_s, y_box_s, x_s + w_s, y_box_s + seg_h_s)
                pill_s = Image.new("RGBA", (w_s, seg_h_s), (0, 0, 0, 0))
                pill_draw = ImageDraw.Draw(pill_s)
                lc = _hex_to_rgb("#FFD24A")
                rc = _hex_to_rgb("#FF7A18")
                for pi in range(w_s):
                    t = pi / max(1, w_s - 1)
                    pill_draw.line([(pi, 0), (pi, seg_h_s)],
                                   fill=_lerp_color(lc, rc, t) + (235,))
                pill_mask_s = Image.new("L", (w_s, seg_h_s), 0)
                rad_s = max(8 * S, seg_h_s // 2)
                ImageDraw.Draw(pill_mask_s).rounded_rectangle(
                    (0, 0, w_s - 1, seg_h_s - 1), radius=rad_s, fill=255,
                )
                sharp_s.paste(pill_s, (int(x_s), int(y_box_s)), pill_mask_s)
                sd.rounded_rectangle(rect_s, radius=rad_s,
                                     outline=(255, 245, 170, 230), width=S)
                txt_x_s = x_s + item["pill_pad_x"] * S - bbox[0] * S
                txt_y_s = y_box_s + item["pill_pad_y"] * S - bbox[1] * S
                self._draw_text(sd, (txt_x_s, txt_y_s), item["text"],
                                (20, 20, 20, 255), bold=True, hi=True)
            else:
                rgb = _hex_to_rgb(str(item["color"])) if item.get("color") else metric_rgb
                txt_y_s = cy_s - item["th"] * S // 2 - bbox[1] * S
                # Center the text block within its reserved slot.
                # item["w"]  = max(actual_text_w, min_text_w) — the stable slot width.
                # item["tw"] = actual rendered text width (may be < slot when value is short).
                # Half the spare space goes on each side → text is horizontally centred.
                center_off_s = (item["w"] - item["tw"]) * S // 2
                draw_x_s = x_s + center_off_s - bbox[0] * S
                if item.get("has_split"):
                    lw_s = item["label_w"] * S
                    vx_s = x_s + center_off_s + lw_s - item["value_bbox"][0] * S
                    if T.transparent_background:
                        keyed_text.append((draw_x_s, txt_y_s, item["label_part"], rgb, False))
                        keyed_text.append((vx_s, txt_y_s, item["value_part"], rgb, True))
                    else:
                        # Glow dùng cùng màu text (rgb) ở opacity thấp → halo mềm,
                        # không tạo viền tương phản màu như T.glow_rgb (magenta).
                        self._draw_text(gd, (draw_x_s, txt_y_s), item["label_part"],
                                        rgb + (160,), hi=True)
                        self._draw_text(sd, (draw_x_s, txt_y_s), item["label_part"],
                                        rgb + (255,), hi=True)
                        self._draw_text(gd, (vx_s, txt_y_s), item["value_part"],
                                        rgb + (160,), bold=True, hi=True)
                        self._draw_text(sd, (vx_s, txt_y_s), item["value_part"],
                                        rgb + (255,), bold=True, hi=True)
                else:
                    if T.transparent_background:
                        keyed_text.append((draw_x_s, txt_y_s, item["text"], rgb, False))
                    else:
                        self._draw_text(gd, (draw_x_s, txt_y_s), item["text"],
                                        rgb + (160,), hi=True)
                        self._draw_text(sd, (draw_x_s, txt_y_s), item["text"],
                                        rgb + (255,), hi=True)
            x_s += item["w"] * S

        glow_s = glow_s.filter(ImageFilter.GaussianBlur(radius=T.glow_radius * S))
        final_s = Image.alpha_composite(bg_s, glow_s)
        final_s = Image.alpha_composite(final_s, sharp_s)
        flat_s = Image.new("RGB", (Ws, Hs), (0, 0, 0))
        flat_s.paste(final_s, (0, 0), final_s.split()[3])
        for tx, ty, kt_text, kt_rgb, kt_bold in keyed_text:
            self._draw_keyed_text(flat_s, (tx, ty), kt_text, kt_rgb, bold=kt_bold, hi=True)

        # Downscale → font mịn (LANCZOS)
        result = flat_s.resize((W, H), Image.LANCZOS)
        if T.transparent_background:
            # Transparent mode: strip LANCZOS fringe pixels so transparentcolor
            # can remove them. Pill mode is NOT stripped (background is intentional).
            result = _strip_fringe(result)
        return result


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

        # Root chỉ làm event-loop/scheduler ẩn. Overlay là một Toplevel riêng
        # để GUI Control Panel không thể withdraw/minimize nhầm cửa sổ overlay.
        self.root = tk.Tk()
        self.root.withdraw()
        self.window = tk.Toplevel(self.root)
        self.window.title("WWM Overlay")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", self._theme.window_alpha)
        self.window.configure(bg="black")

        self.canvas = tk.Canvas(
            self.window, width=200, height=40,
            bg="black", highlightthickness=0, bd=0, takefocus=0,
        )
        self.canvas.pack()
        self._photo: ImageTk.PhotoImage | None = None
        self._img_item = self.canvas.create_image(0, 0, anchor="nw")
        self._last_render_key: tuple[str, tuple[int, int, int], int] | None = None
        self._last_window_size: tuple[int, int] | None = None
        self._last_window_pos: tuple[int, int] | None = None
        self._last_topmost_ts: float = 0.0
        self._topmost_interval_s: float = 2.0

        # Fallback vị trí khi chưa có client area của game
        self.window.geometry(f"+{30}+{30}")
        self._apply_transparent_background()

        # Hide khỏi taskbar sau khi window đã map
        self.window.update_idletasks()
        hwnd = self._hwnd()
        _hide_from_taskbar(hwnd)
        self.window.withdraw()

        # Bindings: Ctrl+drag để move, click thuần KHÔNG làm gì (giữ cho
        # tray double-click toggle). ButtonRelease-1 luôn xử lý để kết
        # thúc drag dù user buông Ctrl trước.
        self.canvas.bind("<Control-ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<Control-B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)
        apply_custom_cursor(self.root)
        apply_custom_cursor(self.window)

        self._visible = False
        self.set_text("Khởi tạo...")

    def _hwnd(self) -> int:
        try:
            self.window.update_idletasks()
            hwnd = int(self.window.winfo_id())
            user32 = ctypes.windll.user32
            user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            user32.GetAncestor.restype = ctypes.c_void_p
            root = user32.GetAncestor(ctypes.c_void_p(hwnd), GA_ROOT)
            return int(root or hwnd)
        except Exception:
            return 0

    def _force_topmost(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if (
            not force
            and self._visible
            and now - self._last_topmost_ts < self._topmost_interval_s
        ):
            return
        try:
            self.window.deiconify()
        except Exception:
            pass
        try:
            self.window.attributes("-topmost", False)
            self.window.attributes("-topmost", True)
        except Exception:
            pass
        try:
            hwnd = self._hwnd()
            user32 = ctypes.windll.user32
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SetWindowPos.restype = ctypes.c_bool
            user32.SetWindowPos(
                ctypes.c_void_p(hwnd),
                ctypes.c_void_p(HWND_TOPMOST),
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        except Exception:
            pass
        try:
            self.window.lift()
        except Exception:
            pass
        self._last_topmost_ts = now

    def _apply_transparent_background(self) -> None:
        try:
            # Luôn giữ black là màu xuyên thấu để phần ngoài rounded
            # background không bị thành hình chữ nhật đen. Checkbox chỉ
            # quyết định renderer có vẽ nền gradient hay không.
            self.window.attributes("-transparentcolor", "black")
        except Exception:
            pass

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
        render_key = ("text", text, self._theme.render_key())
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
            geom = self.window.geometry()
            if "x" in geom and "+" in geom:
                _size, pos = geom.split("+", 1)  # "WxH", "X+Y"
                size = (img.width, img.height)
                if size != self._last_window_size:
                    self.window.geometry(f"{img.width}x{img.height}+{pos}")
                    self._last_window_size = size
        except Exception:
            pass

    def set_segments(self, segments: list[dict[str, Any]], color: str | None = None) -> None:
        """Render multiple overlay segments; event segments get a visual badge."""
        clean_segments = [
            {
                "text": str(seg.get("text") or ""),
                "kind": str(seg.get("kind") or "metric"),
                "color": seg.get("color"),
                "min_text": seg.get("min_text"),
            }
            for seg in segments
            if str(seg.get("text") or "")
        ]
        render_key = (
            "segments",
            tuple(
                (
                    seg["text"],
                    seg["kind"],
                    str(seg.get("color") or ""),
                    str(seg.get("min_text") or ""),
                )
                for seg in clean_segments
            ),
            color or "",
            self._theme.render_key(),
        )
        if render_key == self._last_render_key:
            return
        try:
            img = self._renderer.render_segments(clean_segments, color)
        except Exception as e:
            print(f"[overlay] segment render error: {e}")
            return
        self._photo = ImageTk.PhotoImage(img)
        self._last_render_key = render_key
        self.canvas.configure(width=img.width, height=img.height)
        self.canvas.itemconfigure(self._img_item, image=self._photo)
        try:
            geom = self.window.geometry()
            if "x" in geom and "+" in geom:
                _size, pos = geom.split("+", 1)
                size = (img.width, img.height)
                if size != self._last_window_size:
                    self.window.geometry(f"{img.width}x{img.height}+{pos}")
                    self._last_window_size = size
        except Exception:
            pass

    def set_theme(self, theme_cfg: dict | None,
                  overlay_cfg: dict | None) -> None:
        self._theme = _Theme(theme_cfg, overlay_cfg)
        self._renderer.update_theme(self._theme)
        self._last_render_key = None
        try:
            self.window.attributes("-alpha", self._theme.window_alpha)
        except Exception:
            pass
        self._apply_transparent_background()

    def set_offset(self, x: int, y: int) -> None:
        self._offset = (int(x), int(y))

    def move_to_client(self, x: int, y: int) -> None:
        """Đặt overlay sát góc trên-trái client area của cửa sổ game."""
        if self._drag is not None:
            return  # đang user kéo, không cướp vị trí
        self._last_client_xy = (int(x), int(y))
        try:
            ox, oy = self._offset
            target = (int(x) + ox, int(y) + oy)
            left, top, right, bottom = _virtual_screen_bounds()
            # Một số game/splash trả client origin tạm thời ngoài desktop.
            # Clamp nhẹ để overlay không biến mất khỏi vùng nhìn thấy.
            target = (
                min(max(target[0], left + 2), max(left + 2, right - 20)),
                min(max(target[1], top + 2), max(top + 2, bottom - 20)),
            )
            if target == self._last_window_pos:
                self._force_topmost()
                return
            self.window.geometry(f"+{target[0]}+{target[1]}")
            self._last_window_pos = target
            self._force_topmost(force=True)
        except Exception:
            pass

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def hide(self) -> None:
        try:
            self.window.withdraw()
        except Exception:
            pass
        self._visible = False

    def show(self) -> None:
        self._force_topmost()
        self._visible = True

    def is_visible(self) -> bool:
        return self._visible

    def close(self) -> None:
        try:
            self.window.destroy()
        except Exception:
            pass
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
            self.window.update_idletasks()
            return int(self.window.winfo_x()), int(self.window.winfo_y())
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
            self.window.geometry(f"+{nx}+{ny}")
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
            self.window.attributes("-alpha",
                                 min(1.0, self._theme.window_alpha + 0.05))
        except Exception:
            pass

    def _on_leave(self, _e) -> None:
        try:
            self.window.attributes("-alpha", self._theme.window_alpha)
        except Exception:
            pass
