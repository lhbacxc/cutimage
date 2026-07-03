from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Callable

import numpy as np

ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.image_processor import build_final_image, list_image_files, process_image, save_rgb_image
from core.models import ProcessingSettings
from top_extension_renderer import ExtensionConfig, extend_cuvette_top


def main() -> None:
    args = _parse_args()
    config_path = _resolve_config_path(args.config)
    run_experiment(config_path, logger=print)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CutImage 比色皿上半部分补齐实验")
    parser.add_argument(
        "--config",
        default="config.json",
        help="配置文件路径，默认相对于实验目录解析",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _resolve_config_path(value: str | Path) -> Path:
    path = Path(value)
    return (ROOT_DIR / path).resolve() if not path.is_absolute() else path.resolve()


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return (ROOT_DIR / path).resolve() if not path.is_absolute() else path


def _build_processing_settings(overrides: dict | None) -> ProcessingSettings:
    settings = ProcessingSettings()
    if not overrides:
        return settings

    valid_fields = {field.name for field in fields(ProcessingSettings)}
    for key, value in overrides.items():
        if key in valid_fields:
            setattr(settings, key, value)
    return settings


def _compose_side_by_side(left: np.ndarray, right: np.ndarray, gap: int) -> np.ndarray:
    height = max(left.shape[0], right.shape[0])
    width = left.shape[1] + right.shape[1] + gap
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[: left.shape[0], : left.shape[1]] = left
    canvas[: right.shape[0], left.shape[1] + gap : left.shape[1] + gap + right.shape[1]] = right
    return canvas


def run_experiment(
    config_path: Path,
    logger: Callable[[str], None] | None = None,
) -> dict[str, object]:
    config = _load_json(config_path)

    input_dir = _resolve_path(str(config.get("input_dir", "../image")))
    output_dir = _resolve_path(str(config.get("output_dir", "sample_output")))
    debug_dir = _resolve_path(str(config.get("debug_dir", "debug_output")))
    output_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    files = list_image_files(input_dir)
    limit = int(config.get("limit", 0) or 0)
    if limit > 0:
        files = files[:limit]
    if not files:
        raise RuntimeError(f"未在目录中找到可处理图片: {input_dir}")

    settings = _build_processing_settings(config.get("processing_settings", {}))
    extension_config = ExtensionConfig.from_dict(config.get("extension"))
    save_debug = bool(config.get("save_debug_images", True))
    build_combined = bool(config.get("build_combined_image", True))

    original_output_dir = output_dir / "cropped_original"
    extended_output_dir = output_dir / "cropped_extended"
    original_output_dir.mkdir(parents=True, exist_ok=True)
    extended_output_dir.mkdir(parents=True, exist_ok=True)

    original_crops: list[np.ndarray] = []
    extended_crops: list[np.ndarray] = []

    _log(logger, f"开始处理 {len(files)} 张图片")
    for image_path in files:
        _log(logger, f"处理中: {image_path.name}")
        result = process_image(image_path, settings)
        original_crop = result.crop_rgb
        extended_crop = extend_cuvette_top(original_crop, extension_config)

        original_crops.append(original_crop)
        extended_crops.append(extended_crop)

        output_name = f"{image_path.stem}.png"
        save_rgb_image(original_crop, original_output_dir / output_name)
        save_rgb_image(extended_crop, extended_output_dir / output_name)

        if save_debug:
            comparison = _compose_side_by_side(original_crop, extended_crop, gap=16)
            save_rgb_image(comparison, debug_dir / f"{image_path.stem}_compare.png")

    final_original_path = output_dir / "final_original.png"
    final_extended_path = output_dir / "final_extended.png"
    if build_combined:
        _log(logger, "正在生成拼接图")
        original_final = build_final_image(original_crops, settings)
        extended_final = build_final_image(extended_crops, settings)
        save_rgb_image(original_final, final_original_path)
        save_rgb_image(extended_final, final_extended_path)
        if save_debug:
            final_compare = _compose_side_by_side(original_final, extended_final, gap=24)
            save_rgb_image(final_compare, debug_dir / "final_compare.png")

    _log(logger, f"实验输出目录: {output_dir}")
    _log(logger, f"调试输出目录: {debug_dir}")
    return {
        "config_path": config_path,
        "input_dir": input_dir,
        "output_dir": output_dir,
        "debug_dir": debug_dir,
        "file_count": len(files),
        "final_original_path": final_original_path if build_combined else None,
        "final_extended_path": final_extended_path if build_combined else None,
    }


def _log(logger: Callable[[str], None] | None, message: str) -> None:
    if logger is not None:
        logger(message)


if __name__ == "__main__":
    main()
