from __future__ import annotations

import json
import os
from pathlib import Path

from core.models import ImageState, ProjectData, ProcessingSettings


PROJECT_VERSION = 1


def save_project(project: ProjectData, project_file: Path) -> None:
    project_file.parent.mkdir(parents=True, exist_ok=True)
    base_dir = project_file.parent

    data = {
        "version": PROJECT_VERSION,
        "project_name": project.project_name,
        "source_dir": _relative_path(project.source_dir, base_dir),
        "output_dir": _relative_path(project.output_dir, base_dir) if project.output_dir else None,
        "final_image_name": project.final_image_name,
        "final_image_name_sync_with_project": project.final_image_name_sync_with_project,
        "export_cropped_images": project.export_cropped_images,
        "settings": project.settings.to_dict(),
        "images": [image.to_dict() for image in project.images],
    }
    project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(project_file: Path) -> ProjectData:
    base_dir = project_file.parent
    data = json.loads(project_file.read_text(encoding="utf-8"))

    source_dir = _resolve_path(base_dir, data["source_dir"])
    output_dir = _resolve_path(base_dir, data["output_dir"]) if data.get("output_dir") else None
    settings = ProcessingSettings.from_dict(data.get("settings"))
    images = [ImageState.from_dict(item) for item in data.get("images", [])]

    return ProjectData(
        project_name=str(data.get("project_name", project_file.stem)),
        source_dir=source_dir,
        output_dir=output_dir,
        final_image_name=str(data.get("final_image_name", "")),
        final_image_name_sync_with_project=bool(data.get("final_image_name_sync_with_project", True)),
        export_cropped_images=bool(data.get("export_cropped_images", True)),
        settings=settings,
        images=images,
    )


def _relative_path(target: Path, base_dir: Path) -> str:
    try:
        return os.path.relpath(target.resolve(), base_dir.resolve())
    except ValueError:
        return str(target.resolve())


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()
