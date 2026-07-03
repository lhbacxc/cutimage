from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class ExtensionConfig:
    enabled: bool = True
    extension_height: int = 96
    inner_arc_depth: int = 28
    side_wall_width: int = 16
    top_border_height: int = 6
    blend_height: int = 24
    highlight_strength: float = 0.85
    highlight_width: int = 18

    @classmethod
    def from_dict(cls, data: dict | None) -> "ExtensionConfig":
        if not data:
            return cls()
        return cls(
            enabled=bool(data.get("enabled", True)),
            extension_height=max(0, int(data.get("extension_height", 96))),
            inner_arc_depth=max(1, int(data.get("inner_arc_depth", 28))),
            side_wall_width=max(1, int(data.get("side_wall_width", 16))),
            top_border_height=max(1, int(data.get("top_border_height", 6))),
            blend_height=max(0, int(data.get("blend_height", 24))),
            highlight_strength=float(data.get("highlight_strength", 0.85)),
            highlight_width=max(1, int(data.get("highlight_width", 18))),
        )


def extend_cuvette_top(crop_rgb: np.ndarray, config: ExtensionConfig) -> np.ndarray:
    if not config.enabled or config.extension_height <= 0:
        return crop_rgb.copy()

    height, width = crop_rgb.shape[:2]
    extension_height = min(max(8, config.extension_height), max(8, height * 2))
    side_wall_width = min(max(2, config.side_wall_width), max(2, width // 4))
    top_border_height = min(max(1, config.top_border_height), max(1, extension_height // 3))
    blend_height = min(max(0, config.blend_height), max(0, min(height, extension_height)))
    inner_arc_depth = min(max(4, config.inner_arc_depth), max(4, extension_height - top_border_height))
    highlight_width = min(max(1, config.highlight_width), max(1, extension_height // 2))
    highlight_strength = float(np.clip(config.highlight_strength, 0.0, 1.5))

    palette = _sample_palette(crop_rgb)
    total_height = height + extension_height
    extended = np.zeros((total_height, width, 3), dtype=np.uint8)

    _fill_extension_gradient(extended[:extension_height], palette)
    extended[extension_height:] = crop_rgb
    _blend_transition_band(extended, crop_rgb, extension_height, blend_height, palette)
    _draw_glass_walls(extended, side_wall_width, palette)
    _draw_top_border(extended, extension_height, side_wall_width, top_border_height, palette)
    _draw_inner_cavity(
        extended,
        extension_height,
        side_wall_width,
        top_border_height,
        inner_arc_depth,
        palette,
    )
    _draw_arc_highlight(
        extended,
        extension_height,
        side_wall_width,
        inner_arc_depth,
        highlight_width,
        highlight_strength,
        palette,
    )
    return extended


def _sample_palette(crop_rgb: np.ndarray) -> dict[str, np.ndarray]:
    strip_height = max(1, min(crop_rgb.shape[0], 40))
    strip = crop_rgb[:strip_height]
    mean_color = strip.mean(axis=(0, 1)).astype(np.float32)
    bright_color = np.percentile(strip, 92, axis=(0, 1)).astype(np.float32)
    cool_shadow = np.array([6.0, 10.0, 20.0], dtype=np.float32)

    glow = np.clip(mean_color * 0.8 + bright_color * 0.35, 0, 255)
    glass = np.clip(bright_color * 0.65 + np.array([40.0, 55.0, 90.0], dtype=np.float32), 0, 255)
    border = np.clip(bright_color * 0.85 + np.array([55.0, 55.0, 55.0], dtype=np.float32), 0, 255)
    return {
        "shadow": cool_shadow,
        "glow": glow,
        "glass": glass,
        "border": border,
    }


def _fill_extension_gradient(region: np.ndarray, palette: dict[str, np.ndarray]) -> None:
    height = region.shape[0]
    for row in range(height):
        mix = row / max(height - 1, 1)
        color = palette["shadow"] * (1.0 - mix) + palette["glow"] * (0.15 + mix * 0.55)
        region[row, :] = np.clip(color, 0, 255).astype(np.uint8)


def _blend_transition_band(
    extended: np.ndarray,
    crop_rgb: np.ndarray,
    extension_height: int,
    blend_height: int,
    palette: dict[str, np.ndarray],
) -> None:
    if blend_height <= 0:
        return

    for offset in range(blend_height):
        alpha = 1.0 - (offset / max(blend_height - 1, 1))
        tint = palette["glow"] * (0.32 * alpha) + palette["shadow"] * (0.68 * alpha)
        target_row = extension_height + offset
        base_row = crop_rgb[offset].astype(np.float32)
        mixed = base_row * (1.0 - 0.28 * alpha) + tint
        extended[target_row] = np.clip(mixed, 0, 255).astype(np.uint8)


def _draw_glass_walls(canvas: np.ndarray, side_wall_width: int, palette: dict[str, np.ndarray]) -> None:
    height, width = canvas.shape[:2]
    wall_layer = np.zeros_like(canvas)
    glass_fill = np.clip(palette["glass"] * 0.75, 0, 255).astype(np.uint8).tolist()

    cv2.rectangle(wall_layer, (0, 0), (side_wall_width, height - 1), glass_fill, -1)
    cv2.rectangle(wall_layer, (width - side_wall_width - 1, 0), (width - 1, height - 1), glass_fill, -1)

    wall_layer = cv2.GaussianBlur(wall_layer, (0, 0), sigmaX=3.2, sigmaY=3.2)
    blended = canvas.astype(np.float32) * 0.84 + wall_layer.astype(np.float32) * 0.32
    canvas[:] = np.clip(blended, 0, 255).astype(np.uint8)

    border_color = np.clip(palette["border"], 0, 255).astype(np.uint8).tolist()
    bright_color = np.clip(palette["border"] * 0.92 + 12, 0, 255).astype(np.uint8).tolist()
    x_positions = [
        side_wall_width,
        min(width - 1, side_wall_width + 3),
        max(0, width - side_wall_width - 1),
        max(0, width - side_wall_width - 4),
    ]
    for index, x_pos in enumerate(x_positions):
        color = bright_color if index in {0, 2} else border_color
        cv2.line(canvas, (x_pos, 0), (x_pos, height - 1), color, 1, lineType=cv2.LINE_AA)


def _draw_top_border(
    canvas: np.ndarray,
    extension_height: int,
    side_wall_width: int,
    top_border_height: int,
    palette: dict[str, np.ndarray],
) -> None:
    width = canvas.shape[1]
    y = min(extension_height - 1, top_border_height)
    color = np.clip(palette["border"], 0, 255).astype(np.uint8).tolist()
    cv2.line(
        canvas,
        (side_wall_width, y),
        (max(side_wall_width, width - side_wall_width - 1), y),
        color,
        max(1, top_border_height // 2),
        lineType=cv2.LINE_AA,
    )


def _draw_inner_cavity(
    canvas: np.ndarray,
    extension_height: int,
    side_wall_width: int,
    top_border_height: int,
    inner_arc_depth: int,
    palette: dict[str, np.ndarray],
) -> None:
    height, width = canvas.shape[:2]
    cavity_left = min(width - 2, side_wall_width + 3)
    cavity_right = max(cavity_left + 2, width - side_wall_width - 4)
    cavity_top = min(extension_height - 1, top_border_height + 2)
    arc_center_y = max(cavity_top + 2, extension_height - inner_arc_depth)
    arc_axes_x = max(4, (cavity_right - cavity_left) // 2)
    arc_axes_y = max(3, inner_arc_depth)

    cv2.rectangle(canvas, (cavity_left, cavity_top), (cavity_right, arc_center_y), (0, 0, 0), -1)
    cv2.ellipse(
        canvas,
        ((cavity_left + cavity_right) // 2, arc_center_y),
        (arc_axes_x, arc_axes_y),
        0,
        0,
        180,
        (0, 0, 0),
        -1,
        lineType=cv2.LINE_AA,
    )

    cavity_line = np.clip(palette["border"] * 0.75, 0, 255).astype(np.uint8).tolist()
    cv2.ellipse(
        canvas,
        ((cavity_left + cavity_right) // 2, arc_center_y),
        (max(2, arc_axes_x - 1), max(2, arc_axes_y - 1)),
        0,
        0,
        180,
        cavity_line,
        1,
        lineType=cv2.LINE_AA,
    )


def _draw_arc_highlight(
    canvas: np.ndarray,
    extension_height: int,
    side_wall_width: int,
    inner_arc_depth: int,
    highlight_width: int,
    highlight_strength: float,
    palette: dict[str, np.ndarray],
) -> None:
    height, width = canvas.shape[:2]
    arc_layer = np.zeros_like(canvas)
    center_x = width // 2
    center_y = max(2, extension_height - inner_arc_depth + highlight_width // 3)
    axes_x = max(6, width // 2 - side_wall_width - 8)
    axes_y = max(4, highlight_width)
    color = np.clip(palette["glow"] * (0.85 + highlight_strength * 0.35), 0, 255).astype(np.uint8).tolist()

    cv2.ellipse(
        arc_layer,
        (center_x, min(height - 2, center_y)),
        (axes_x, axes_y),
        0,
        8,
        172,
        color,
        max(1, highlight_width // 3),
        lineType=cv2.LINE_AA,
    )
    arc_layer = cv2.GaussianBlur(arc_layer, (0, 0), sigmaX=5.0, sigmaY=5.0)
    blended = canvas.astype(np.float32) + arc_layer.astype(np.float32) * min(1.0, 0.55 + highlight_strength * 0.2)
    canvas[:] = np.clip(blended, 0, 255).astype(np.uint8)
