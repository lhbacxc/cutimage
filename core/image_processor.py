from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from core.models import ProcessingSettings, Rect


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
FINAL_IMAGE_SIZE_MODES = {"original", "target_height"}


class ImageProcessingError(Exception):
    pass


@dataclass
class ProcessedImage:
    filename: str
    rect: Rect
    crop_rgb: np.ndarray
    status: str
    message: str


def list_image_files(source_dir: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in source_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ],
        key=lambda path: path.name.lower(),
    )


def read_image(path: Path) -> np.ndarray:
    buffer = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ImageProcessingError(f"无法读取图片: {path.name}")
    return image


def detect_crop_rect(image_bgr: np.ndarray, settings: ProcessingSettings) -> Rect:
    max_channel = image_bgr.max(axis=2)
    loose_threshold = max(10, int(settings.threshold))
    tight_threshold = min(255, max(loose_threshold + 10, loose_threshold * 2))

    loose_mask = _build_mask(max_channel, loose_threshold, close_kernel=7)
    tight_mask = _build_mask(max_channel, tight_threshold, close_kernel=5)
    combined_mask = cv2.bitwise_or(loose_mask, tight_mask)

    contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [cnt for cnt in contours if cv2.contourArea(cnt) > 100]
    if not contours:
        raise ImageProcessingError("未检测到有效目标区域")

    best_contour = max(contours, key=lambda cnt: _contour_score(cnt, image_bgr.shape))
    x, y, w, h = cv2.boundingRect(best_contour)
    base_rect = Rect(x, y, w, h)
    refined = _refine_rect_with_projection(loose_mask, base_rect)

    padding = max(0, int(settings.padding))
    # 顶部和左右稍多留一点，保留比色皿轮廓；底部适度克制，减少无效黑边。
    padded = Rect(
        refined.x - padding,
        refined.y - (padding + 4),
        refined.width + padding * 2,
        refined.height + padding * 2 + 2,
    )
    return padded.clamp(image_bgr.shape[1], image_bgr.shape[0])


def crop_image(image_bgr: np.ndarray, rect: Rect) -> np.ndarray:
    safe = rect.clamp(image_bgr.shape[1], image_bgr.shape[0])
    if safe.width <= 0 or safe.height <= 0:
        raise ImageProcessingError("裁剪区域无效")
    crop_bgr = image_bgr[safe.y : safe.bottom, safe.x : safe.right]
    return cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)


def process_image(
    image_path: Path,
    settings: ProcessingSettings,
    manual_rect: Rect | None = None,
) -> ProcessedImage:
    image = read_image(image_path)
    rect = manual_rect.clamp(image.shape[1], image.shape[0]) if manual_rect else detect_crop_rect(image, settings)
    crop_rgb = crop_image(image, rect)
    return ProcessedImage(
        filename=image_path.name,
        rect=rect,
        crop_rgb=crop_rgb,
        status="success",
        message="手动修正" if manual_rect else "自动识别",
    )


def apply_shape_style(
    image_rgb: np.ndarray,
    shape_mode: str,
    corner_radius: int,
    background_rgb: tuple[int, int, int],
) -> np.ndarray:
    normalized_mode = shape_mode.lower()
    styled = image_rgb.copy()
    if normalized_mode != "rounded":
        return styled

    radius = clamp_corner_radius(styled.shape[1], styled.shape[0], corner_radius)
    if radius <= 0:
        return styled

    mask = _rounded_mask(styled.shape[1], styled.shape[0], radius)
    background = np.full_like(styled, background_rgb, dtype=np.uint8)
    alpha = (mask.astype(np.float32) / 255.0)[..., None]
    blended = styled.astype(np.float32) * alpha + background.astype(np.float32) * (1.0 - alpha)
    return blended.astype(np.uint8)


def build_final_image(
    crops: list[np.ndarray],
    settings: ProcessingSettings,
    size_mode: str = "target_height",
) -> np.ndarray:
    if not crops:
        raise ImageProcessingError("没有可用于拼接的图片")

    normalized_size_mode = size_mode.strip().lower()
    if normalized_size_mode not in FINAL_IMAGE_SIZE_MODES:
        raise ImageProcessingError(f"涓嶆敮鎸佺殑鎷兼帴灏哄妯″紡: {size_mode}")

    spacing = max(0, int(settings.spacing))
    outer_padding = max(8, spacing)
    background_rgb = _background_rgb(settings.background_mode)
    align_mode = settings.align_mode if settings.align_mode in {"top", "center", "bottom", "stretch"} else "center"
    stretch_to_fit = align_mode == "stretch"
    outline_width = max(0, int(settings.outline_width))
    draw_outline = settings.background_mode == "white" and settings.add_outline_on_white and outline_width > 0

    if stretch_to_fit:
        unified_height = max(1, int(settings.stretch_target_height))
        scale = None
    elif normalized_size_mode == "target_height":
        target_height = max(1, int(settings.target_height))
        max_crop_height = max(crop.shape[0] for crop in crops)
        scale = target_height / max_crop_height
        unified_height = None
    else:
        scale = 1.0
        unified_height = None

    prepared: list[np.ndarray] = []
    total_width = 0
    content_height = 0

    for crop in crops:
        height, width = crop.shape[:2]
        if stretch_to_fit:
            output_width = width
            output_height = unified_height
            if height == output_height:
                output_image = crop
            else:
                output_image = np.array(
                    Image.fromarray(crop).resize((output_width, output_height), Image.Resampling.LANCZOS)
                )
        elif normalized_size_mode == "target_height":
            output_width = max(1, int(round(width * scale)))
            output_height = max(1, int(round(height * scale)))
            output_image = np.array(
                Image.fromarray(crop).resize((output_width, output_height), Image.Resampling.LANCZOS)
            )
        else:
            output_width = width
            output_height = height
            output_image = crop

        output_image = apply_shape_style(
            output_image,
            settings.final_shape_mode,
            settings.final_corner_radius,
            background_rgb,
        )
        prepared.append(output_image)
        total_width += output_width
        content_height = max(content_height, output_height)

    total_width += spacing * max(0, len(prepared) - 1)
    canvas_height = content_height + outer_padding * 2
    canvas_width = total_width + outer_padding * 2
    final = np.full((canvas_height, canvas_width, 3), background_rgb, dtype=np.uint8)

    current_x = outer_padding
    for image in prepared:
        height, width = image.shape[:2]
        if stretch_to_fit:
            offset_y = outer_padding
        else:
            offset_y = outer_padding + _aligned_offset(content_height, height, align_mode)
        final[offset_y : offset_y + height, current_x : current_x + width] = image
        if draw_outline:
            if settings.final_shape_mode == "rounded":
                _draw_rounded_outline(
                    final,
                    current_x,
                    offset_y,
                    width,
                    height,
                    settings.final_corner_radius,
                    (210, 210, 210),
                    outline_width,
                )
            else:
                cv2.rectangle(
                    final,
                    (current_x, offset_y),
                    (current_x + width - 1, offset_y + height - 1),
                    (210, 210, 210),
                    outline_width,
                )
        current_x += width + spacing

    return final


def save_rgb_image(image_rgb: np.ndarray, output_path: Path) -> None:
    if output_path.suffix.lower() != ".png":
        raise ImageProcessingError(f"鍙厑璁稿鍑烘棤鎹 PNG: {output_path.name}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image_rgb).save(output_path, format="PNG")


def to_pil_image(image_rgb: np.ndarray) -> Image.Image:
    return Image.fromarray(image_rgb)


def background_rgb_for_mode(mode: str) -> tuple[int, int, int]:
    return (255, 255, 255) if mode == "white" else (0, 0, 0)


def clamp_corner_radius(width: int, height: int, radius: int) -> int:
    safe_radius = max(0, int(radius))
    return min(safe_radius, max(0, min(width, height) // 2))


def _build_mask(max_channel: np.ndarray, threshold: int, close_kernel: int) -> np.ndarray:
    mask = np.where(max_channel >= threshold, 255, 0).astype(np.uint8)
    kernel = np.ones((close_kernel, close_kernel), dtype=np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8), iterations=1)
    return mask


def _refine_rect_with_projection(mask: np.ndarray, rect: Rect) -> Rect:
    region = mask[rect.y : rect.bottom, rect.x : rect.right]
    if region.size == 0:
        return rect

    row_counts = np.count_nonzero(region, axis=1)
    col_counts = np.count_nonzero(region, axis=0)
    min_row_pixels = max(3, rect.width // 10)
    min_col_pixels = max(3, rect.height // 10)

    top_idx = _first_index(row_counts, min_row_pixels)
    bottom_idx = _last_index(row_counts, min_row_pixels)
    left_idx = _first_index(col_counts, min_col_pixels)
    right_idx = _last_index(col_counts, min_col_pixels)

    if top_idx is None or bottom_idx is None or left_idx is None or right_idx is None:
        return rect

    return Rect(
        rect.x + left_idx,
        rect.y + top_idx,
        max(1, right_idx - left_idx + 1),
        max(1, bottom_idx - top_idx + 1),
    )


def _first_index(values: np.ndarray, minimum: int) -> int | None:
    matches = np.where(values >= minimum)[0]
    if matches.size == 0:
        return None
    return int(matches[0])


def _last_index(values: np.ndarray, minimum: int) -> int | None:
    matches = np.where(values >= minimum)[0]
    if matches.size == 0:
        return None
    return int(matches[-1])


def _background_rgb(mode: str) -> tuple[int, int, int]:
    return background_rgb_for_mode(mode)


def _aligned_offset(canvas_height: int, image_height: int, align_mode: str) -> int:
    if align_mode == "top":
        return 0
    if align_mode == "stretch":
        return 0
    if align_mode == "bottom":
        return canvas_height - image_height
    return max(0, (canvas_height - image_height) // 2)


def _rounded_mask(width: int, height: int, radius: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.rectangle(mask, (radius, 0), (width - radius - 1, height - 1), 255, -1)
    cv2.rectangle(mask, (0, radius), (width - 1, height - radius - 1), 255, -1)
    for center in (
        (radius, radius),
        (width - radius - 1, radius),
        (radius, height - radius - 1),
        (width - radius - 1, height - radius - 1),
    ):
        cv2.circle(mask, center, radius, 255, -1, lineType=cv2.LINE_AA)
    return mask


def _draw_rounded_outline(
    canvas: np.ndarray,
    x: int,
    y: int,
    width: int,
    height: int,
    radius: int,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    safe_radius = clamp_corner_radius(width, height, radius)
    if safe_radius <= 0:
        cv2.rectangle(canvas, (x, y), (x + width - 1, y + height - 1), color, thickness)
        return

    left = x
    top = y
    right = x + width - 1
    bottom = y + height - 1
    radius = safe_radius

    cv2.line(canvas, (left + radius, top), (right - radius, top), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(canvas, (left + radius, bottom), (right - radius, bottom), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(canvas, (left, top + radius), (left, bottom - radius), color, thickness, lineType=cv2.LINE_AA)
    cv2.line(canvas, (right, top + radius), (right, bottom - radius), color, thickness, lineType=cv2.LINE_AA)

    cv2.ellipse(canvas, (left + radius, top + radius), (radius, radius), 180, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(canvas, (right - radius, top + radius), (radius, radius), 270, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(canvas, (left + radius, bottom - radius), (radius, radius), 90, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(canvas, (right - radius, bottom - radius), (radius, radius), 0, 0, 90, color, thickness, cv2.LINE_AA)


def _contour_score(contour: np.ndarray, image_shape: tuple[int, ...]) -> float:
    image_height, image_width = image_shape[:2]
    x, y, width, height = cv2.boundingRect(contour)
    area = float(cv2.contourArea(contour))
    if area <= 0:
        return 0.0

    center_x = (x + width / 2) / image_width
    center_bias = max(0.2, 1.0 - abs(center_x - 0.5) * 2.2)

    aspect_ratio = height / max(width, 1)
    aspect_bias = max(0.2, 1.0 - abs(aspect_ratio - 2.0) / 2.2)

    height_bias = min(1.2, height / max(image_height * 0.18, 1))
    width_bias = 0.4 if width > image_width * 0.28 else 1.0

    return area * center_bias * aspect_bias * height_bias * width_bias
