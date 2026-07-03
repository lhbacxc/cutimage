from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def normalize_output_format(value: Any) -> str:
    normalized = str(value or "png").strip().lower()
    return "png" if normalized == "png" else "png"


def normalize_align_mode(value: Any) -> str:
    normalized = str(value or "center").strip().lower()
    return normalized if normalized in {"top", "center", "bottom", "stretch"} else "center"


@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def clamp(self, max_width: int, max_height: int) -> "Rect":
        left = max(0, min(self.x, max_width - 1))
        top = max(0, min(self.y, max_height - 1))
        right = max(left + 1, min(self.right, max_width))
        bottom = max(top + 1, min(self.bottom, max_height))
        return Rect(left, top, right - left, bottom - top)

    def to_dict(self) -> dict[str, int]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Rect | None":
        if not data:
            return None
        return cls(
            x=int(data["x"]),
            y=int(data["y"]),
            width=int(data["width"]),
            height=int(data["height"]),
        )


@dataclass
class ProcessingSettings:
    threshold: int = 24
    padding: int = 8
    spacing: int = 16
    target_height: int = 280
    stretch_target_height: int = 280
    background_mode: str = "white"
    output_format: str = "png"
    align_mode: str = "stretch"
    crop_shape_mode: str = "rounded"
    crop_corner_radius: int = 18
    final_shape_mode: str = "rounded"
    final_corner_radius: int = 18
    add_outline_on_white: bool = False
    outline_width: int = 1

    def __post_init__(self) -> None:
        self.output_format = normalize_output_format(self.output_format)
        self.align_mode = normalize_align_mode(self.align_mode)
        self.target_height = max(1, int(self.target_height))
        self.stretch_target_height = max(1, int(self.stretch_target_height))

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "padding": self.padding,
            "spacing": self.spacing,
            "target_height": self.target_height,
            "stretch_target_height": self.stretch_target_height,
            "background_mode": self.background_mode,
            "output_format": self.output_format,
            "align_mode": self.align_mode,
            "crop_shape_mode": self.crop_shape_mode,
            "crop_corner_radius": self.crop_corner_radius,
            "final_shape_mode": self.final_shape_mode,
            "final_corner_radius": self.final_corner_radius,
            "add_outline_on_white": self.add_outline_on_white,
            "outline_width": self.outline_width,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProcessingSettings":
        if not data:
            return cls()

        background_mode = str(data.get("background_mode", "")).lower()
        if not background_mode:
            legacy_color = str(data.get("background_color", "#000000")).lower()
            background_mode = "white" if legacy_color == "#ffffff" else "black"

        target_height = int(data.get("target_height", 280))
        stretch_target_height = int(data.get("stretch_target_height", target_height))

        return cls(
            threshold=int(data.get("threshold", 24)),
            padding=int(data.get("padding", 8)),
            spacing=int(data.get("spacing", 16)),
            target_height=target_height,
            stretch_target_height=stretch_target_height,
            background_mode=background_mode if background_mode in {"black", "white"} else "black",
            output_format=normalize_output_format(data.get("output_format", "png")),
            align_mode=normalize_align_mode(data.get("align_mode", "center")),
            crop_shape_mode=str(data.get("crop_shape_mode", "square")).lower(),
            crop_corner_radius=int(data.get("crop_corner_radius", 18)),
            final_shape_mode=str(data.get("final_shape_mode", "square")).lower(),
            final_corner_radius=int(data.get("final_corner_radius", 18)),
            add_outline_on_white=bool(data.get("add_outline_on_white", False)),
            outline_width=int(data.get("outline_width", 1)),
        )


@dataclass
class ImageState:
    filename: str
    auto_rect: Rect | None = None
    manual_rect: Rect | None = None
    status: str = "pending"
    message: str = ""

    @property
    def effective_rect(self) -> Rect | None:
        return self.manual_rect or self.auto_rect

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "auto_rect": self.auto_rect.to_dict() if self.auto_rect else None,
            "manual_rect": self.manual_rect.to_dict() if self.manual_rect else None,
            "status": self.status,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImageState":
        return cls(
            filename=str(data["filename"]),
            auto_rect=Rect.from_dict(data.get("auto_rect")),
            manual_rect=Rect.from_dict(data.get("manual_rect")),
            status=str(data.get("status", "pending")),
            message=str(data.get("message", "")),
        )


@dataclass
class ProjectData:
    project_name: str
    source_dir: Path
    output_dir: Path | None = None
    final_image_name: str = ""
    final_image_name_sync_with_project: bool = True
    settings: ProcessingSettings = field(default_factory=ProcessingSettings)
    images: list[ImageState] = field(default_factory=list)

    def image_map(self) -> dict[str, ImageState]:
        return {item.filename: item for item in self.images}

    def sorted_filenames(self) -> list[str]:
        return [item.filename for item in self.images]
