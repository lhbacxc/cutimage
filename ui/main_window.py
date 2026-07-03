from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageTk

from core.image_processor import (
    ImageProcessingError,
    apply_shape_style,
    background_rgb_for_mode,
    build_final_image,
    crop_image,
    list_image_files,
    process_image,
    read_image,
    save_rgb_image,
    to_pil_image,
)
from core.models import ImageState, ProcessingSettings, ProjectData, Rect
from core.project_store import load_project, save_project


BACKGROUND_LABELS = {
    "纯黑": "black",
    "纯白": "white",
}

ALIGN_LABELS = {
    "顶部对齐": "top",
    "居中对齐": "center",
    "底部对齐": "bottom",
    "上下对齐（拉伸）": "stretch",
}

SHAPE_LABELS = {
    "直角矩形": "square",
    "圆角矩形": "rounded",
}

STATUS_LABELS = {
    "failed": "失败",
    "missing": "缺失",
    "success": "完成",
}

INVALID_FILENAME_CHARS = '<>:"/\\|?*'


class CutImageApp:
    HANDLE_RADIUS = 6
    EDGE_HIT_WIDTH = 10

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("CutImage 桌面工具")
        self.root.geometry("1500x920")
        self.root.minsize(1280, 780)
        self.style = ttk.Style(self.root)
        self.style.configure("Thumbnail.Treeview", rowheight=104)

        self.project: ProjectData | None = None
        self.project_file: Path | None = None
        self.processed_crops: dict[str, np.ndarray] = {}
        self.original_cache: dict[str, np.ndarray] = {}
        self.thumbnail_cache: dict[str, ImageTk.PhotoImage] = {}
        self.current_image_photo: ImageTk.PhotoImage | None = None
        self.current_crop_photo: ImageTk.PhotoImage | None = None
        self.final_preview_photo: ImageTk.PhotoImage | None = None
        self.display_scale = 1.0
        self.display_offset = (0, 0)
        self.drag_mode: str | None = None
        self.drag_anchor: tuple[int, int] | None = None
        self.drag_start_rect: Rect | None = None
        self.selected_edge: str | None = None
        self._suppress_select_image_reset = False
        self.toolbar_buttons: dict[str, ttk.Button] = {}
        self.project_name_entry: ttk.Entry | None = None
        self.final_image_name_entry: ttk.Entry | None = None
        self.final_image_name_sync_checkbutton: ttk.Checkbutton | None = None
        self._is_processing = False
        self._processing_thread: threading.Thread | None = None
        self._processing_queue: queue.Queue[dict] | None = None
        self._processing_completion_callback: Callable[[], None] | None = None
        self._processing_selected_index: int | None = None

        self._build_variables()
        self._build_layout()
        self.root.after(150, self._draw_placeholder)

    def run(self) -> None:
        self.root.mainloop()

    def _build_variables(self) -> None:
        self.threshold_var = tk.IntVar(value=24)
        self.padding_var = tk.IntVar(value=8)
        self.spacing_var = tk.IntVar(value=16)
        self.target_height_var = tk.IntVar(value=280)
        self.stretch_target_height_var = tk.IntVar(value=280)
        self.background_mode_var = tk.StringVar(value="纯黑")
        self.align_mode_var = tk.StringVar(value="居中对齐")
        self.output_format_var = tk.StringVar(value="png")
        self.add_outline_var = tk.BooleanVar(value=False)
        self.crop_shape_mode_var = tk.StringVar(value="直角矩形")
        self.crop_corner_radius_var = tk.IntVar(value=18)
        self.final_shape_mode_var = tk.StringVar(value="直角矩形")
        self.final_corner_radius_var = tk.IntVar(value=18)
        self.project_name_var = tk.StringVar(value="")
        self.final_image_name_var = tk.StringVar(value="")
        self.final_image_name_sync_var = tk.BooleanVar(value=True)
        self.progress_text_var = tk.StringVar(value="就绪")
        self.progress_value_var = tk.DoubleVar(value=0)
        self.rect_left_var = tk.IntVar(value=0)
        self.rect_top_var = tk.IntVar(value=0)
        self.rect_right_var = tk.IntVar(value=0)
        self.rect_bottom_var = tk.IntVar(value=0)
        self.background_mode_var.set(list(BACKGROUND_LABELS.keys())[1])
        self.align_mode_var.set(list(ALIGN_LABELS.keys())[3])
        self.crop_shape_mode_var.set(list(SHAPE_LABELS.keys())[1])
        self.final_shape_mode_var.set(list(SHAPE_LABELS.keys())[1])

    def _build_layout(self) -> None:
        toolbar = ttk.Frame(self.root, padding=(10, 10, 10, 6))
        toolbar.pack(side=tk.TOP, fill=tk.X)

        buttons = [
            ("新建项目", self.new_project),
            ("打开项目", self.open_project),
            ("保存项目", self.save_project_action),
            ("另存项目", self.save_project_as),
            ("批量处理", self.process_all_images),
            ("导出结果", self.export_results),
        ]
        for text, command in buttons:
            button = ttk.Button(toolbar, text=text, command=command)
            button.pack(side=tk.LEFT, padx=(0, 8))
            self.toolbar_buttons[text] = button

        ttk.Label(toolbar, text="项目名").pack(side=tk.LEFT, padx=(16, 6))
        self.project_name_entry = ttk.Entry(toolbar, textvariable=self.project_name_var, width=24)
        self.project_name_entry.pack(side=tk.LEFT)

        ttk.Label(toolbar, text="最终导出名").pack(side=tk.LEFT, padx=(16, 6))
        self.final_image_name_entry = ttk.Entry(toolbar, textvariable=self.final_image_name_var, width=24)
        self.final_image_name_entry.pack(side=tk.LEFT)
        self.final_image_name_sync_checkbutton = ttk.Checkbutton(
            toolbar,
            text="与项目名一致",
            variable=self.final_image_name_sync_var,
            command=self._on_final_image_name_sync_change,
        )
        self.final_image_name_sync_checkbutton.pack(side=tk.LEFT, padx=(8, 0))
        self._update_export_name_control_state()

        progress_row = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        progress_row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(progress_row, textvariable=self.progress_text_var, width=30).pack(side=tk.LEFT)
        self.progress_bar = ttk.Progressbar(
            progress_row,
            mode="determinate",
            maximum=100,
            variable=self.progress_value_var,
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

        main = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.left_frame = ttk.Frame(main, padding=8)
        self.center_frame = ttk.Frame(main, padding=8)
        self.right_frame = ttk.Frame(main, padding=8)
        main.add(self.left_frame, weight=1)
        main.add(self.center_frame, weight=4)
        main.add(self.right_frame, weight=2)

        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        ttk.Label(self.left_frame, text="图片列表").pack(anchor=tk.W)

        list_frame = ttk.Frame(self.left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 8))

        self.image_tree = ttk.Treeview(list_frame, show="tree", selectmode="browse", style="Thumbnail.Treeview")
        self.image_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.image_tree.bind("<<TreeviewSelect>>", lambda _event: self.on_select_image())

        tree_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.image_tree.yview)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.image_tree.configure(yscrollcommand=tree_scrollbar.set)

        move_frame = ttk.Frame(self.left_frame)
        move_frame.pack(fill=tk.X)
        ttk.Button(move_frame, text="上移", command=lambda: self.move_selected_image(-1)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4)
        )
        ttk.Button(move_frame, text="下移", command=lambda: self.move_selected_image(1)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0)
        )

        ttk.Button(self.left_frame, text="恢复自动排序", command=self.restore_auto_sort).pack(fill=tk.X, pady=(8, 0))

    def _build_center_panel(self) -> None:
        ttk.Label(self.center_frame, text="原图与裁剪框").pack(anchor=tk.W)
        self.image_canvas = tk.Canvas(
            self.center_frame,
            bg="#1e1e1e",
            highlightthickness=1,
            highlightbackground="#444444",
            takefocus=1,
        )
        self.image_canvas.pack(fill=tk.BOTH, expand=True, pady=(6, 8))
        self.image_canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.image_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.image_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.image_canvas.bind("<KeyPress>", self.on_canvas_key_press)

        preview_row = ttk.Frame(self.center_frame)
        preview_row.pack(fill=tk.X)

        crop_frame = ttk.LabelFrame(preview_row, text="当前裁剪结果", padding=8)
        crop_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        self.crop_preview_label = ttk.Label(crop_frame)
        self.crop_preview_label.pack(fill=tk.BOTH, expand=True)

        final_frame = ttk.LabelFrame(preview_row, text="拼接预览", padding=8)
        final_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.final_preview_label = ttk.Label(final_frame)
        self.final_preview_label.pack(fill=tk.BOTH, expand=True)

    def _build_right_panel(self) -> None:
        settings_frame = ttk.LabelFrame(self.right_frame, text="全局参数", padding=8)
        settings_frame.pack(fill=tk.X)
        self._add_labeled_spinbox(settings_frame, "检测阈值", self.threshold_var, 0, 255)
        self._add_labeled_spinbox(settings_frame, "边缘留白", self.padding_var, 0, 200)
        self._add_labeled_spinbox(settings_frame, "图片间距", self.spacing_var, 0, 200)
        self._add_labeled_spinbox(settings_frame, "参考高度", self.target_height_var, 50, 4000)
        self.stretch_target_height_spinbox = self._add_labeled_spinbox(
            settings_frame,
            "拉伸统一高度",
            self.stretch_target_height_var,
            50,
            4000,
            on_change=self.refresh_final_preview,
        )

        self._add_labeled_combobox(settings_frame, "背景", self.background_mode_var, tuple(BACKGROUND_LABELS.keys()))
        self._add_labeled_combobox(
            settings_frame,
            "对齐",
            self.align_mode_var,
            tuple(ALIGN_LABELS.keys()),
            on_change=self._on_align_mode_change,
        )
        self._add_labeled_combobox(settings_frame, "输出格式", self.output_format_var, ("png",))

        ttk.Checkbutton(
            settings_frame,
            text="白底时加细灰边线",
            variable=self.add_outline_var,
            command=self.refresh_previews,
        ).pack(anchor=tk.W, pady=(6, 0))
        ttk.Button(settings_frame, text="刷新预览", command=self.refresh_previews).pack(fill=tk.X, pady=(8, 0))

        crop_style_frame = ttk.LabelFrame(self.right_frame, text="单张裁剪图样式", padding=8)
        crop_style_frame.pack(fill=tk.X, pady=(10, 0))
        self.crop_shape_mode_combo = self._add_labeled_combobox(
            crop_style_frame,
            "形状",
            self.crop_shape_mode_var,
            tuple(SHAPE_LABELS.keys()),
            on_change=self._on_crop_shape_change,
        )
        self.crop_corner_radius_spinbox = self._add_labeled_spinbox(
            crop_style_frame,
            "圆角半径",
            self.crop_corner_radius_var,
            0,
            1000,
        )

        final_style_frame = ttk.LabelFrame(self.right_frame, text="最终拼接图样式", padding=8)
        final_style_frame.pack(fill=tk.X, pady=(10, 0))
        self.final_shape_mode_combo = self._add_labeled_combobox(
            final_style_frame,
            "形状",
            self.final_shape_mode_var,
            tuple(SHAPE_LABELS.keys()),
            on_change=self._on_final_shape_change,
        )
        self.final_corner_radius_spinbox = self._add_labeled_spinbox(
            final_style_frame,
            "圆角半径",
            self.final_corner_radius_var,
            0,
            1000,
        )

        rect_frame = ttk.LabelFrame(self.right_frame, text="单图修正", padding=8)
        rect_frame.pack(fill=tk.X, pady=(10, 0))
        self._add_labeled_spinbox(rect_frame, "左", self.rect_left_var, 0, 100000)
        self._add_labeled_spinbox(rect_frame, "上", self.rect_top_var, 0, 100000)
        self._add_labeled_spinbox(rect_frame, "右", self.rect_right_var, 0, 100000)
        self._add_labeled_spinbox(rect_frame, "下", self.rect_bottom_var, 0, 100000)
        ttk.Button(rect_frame, text="应用边界数值", command=self.apply_manual_rect_from_inputs).pack(
            fill=tk.X, pady=(6, 4)
        )
        ttk.Button(rect_frame, text="清除手动修正", command=self.clear_manual_rect).pack(fill=tk.X)

        log_frame = ttk.LabelFrame(self.right_frame, text="日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log_text = tk.Text(log_frame, height=18, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self._update_control_state()

    def _add_labeled_spinbox(
        self,
        parent: ttk.Widget,
        label: str,
        variable: tk.IntVar,
        minimum: int,
        maximum: int,
        on_change=None,
    ) -> ttk.Spinbox:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=10).pack(side=tk.LEFT)
        spinbox = ttk.Spinbox(row, from_=minimum, to=maximum, textvariable=variable, width=12)
        spinbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if on_change is not None:
            spinbox.configure(command=on_change)
            spinbox.bind("<FocusOut>", lambda _event: on_change())
            spinbox.bind("<Return>", lambda _event: on_change())
        return spinbox

    def _add_labeled_combobox(
        self,
        parent: ttk.Widget,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
        on_change=None,
    ) -> ttk.Combobox:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text=label, width=10).pack(side=tk.LEFT)
        combo = ttk.Combobox(row, state="readonly", textvariable=variable, values=values)
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if on_change is None:
            combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_final_preview())
        else:
            combo.bind("<<ComboboxSelected>>", on_change)
        return combo

    def _start_batch_processing(self, on_complete: Callable[[], None] | None = None) -> bool:
        if not self.ensure_project():
            return False
        if self._is_processing:
            self.log("批量处理正在进行中，请稍候。")
            return False

        self._sync_settings_from_ui()
        assert self.project is not None
        settings_snapshot = ProcessingSettings.from_dict(self.project.settings.to_dict())
        items_snapshot = [{"filename": item.filename, "manual_rect": item.manual_rect} for item in self.project.images]
        if not items_snapshot:
            messagebox.showwarning("没有图片", "当前项目中没有可处理的图片。")
            return False

        self._processing_completion_callback = on_complete
        self._processing_selected_index = self.get_selected_index()
        self._processing_queue = queue.Queue()
        self._set_processing_state(True)
        self.progress_bar.configure(maximum=len(items_snapshot))
        self.progress_value_var.set(0)
        self.progress_text_var.set(f"正在准备批量处理（0 / {len(items_snapshot)}）")

        self._processing_thread = threading.Thread(
            target=self._run_batch_processing_worker,
            args=(self.project.source_dir, settings_snapshot, items_snapshot, self._processing_queue),
            daemon=True,
        )
        self._processing_thread.start()
        self.root.after(60, self._poll_processing_queue)
        return True

    def _run_batch_processing_worker(
        self,
        source_dir: Path,
        settings: ProcessingSettings,
        items_snapshot: list[dict],
        message_queue: queue.Queue[dict],
    ) -> None:
        processed_crops: dict[str, np.ndarray] = {}
        item_updates: dict[str, dict] = {}
        success_count = 0
        failure_count = 0
        total = len(items_snapshot)

        try:
            for index, item in enumerate(items_snapshot, start=1):
                filename = str(item["filename"])
                manual_rect = item["manual_rect"]
                image_path = source_dir / filename

                if not image_path.exists():
                    item_updates[filename] = {
                        "status": "missing",
                        "message": "原图缺失",
                        "auto_rect": None,
                        "update_auto_rect": False,
                    }
                    failure_count += 1
                    message_queue.put(
                        {
                            "type": "progress",
                            "current": index,
                            "total": total,
                            "filename": filename,
                            "status_text": "原图缺失",
                        }
                    )
                    continue

                try:
                    result = process_image(image_path, settings, manual_rect)
                    processed_crops[filename] = result.crop_rgb
                    item_updates[filename] = {
                        "status": "success",
                        "message": result.message,
                        "auto_rect": result.rect,
                        "update_auto_rect": manual_rect is None,
                    }
                    success_count += 1
                    status_text = "处理完成"
                except ImageProcessingError as exc:
                    item_updates[filename] = {
                        "status": "failed",
                        "message": str(exc),
                        "auto_rect": None,
                        "update_auto_rect": False,
                    }
                    failure_count += 1
                    status_text = str(exc)

                message_queue.put(
                    {
                        "type": "progress",
                        "current": index,
                        "total": total,
                        "filename": filename,
                        "status_text": status_text,
                    }
                )

            message_queue.put(
                {
                    "type": "done",
                    "processed_crops": processed_crops,
                    "item_updates": item_updates,
                    "success_count": success_count,
                    "failure_count": failure_count,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive UI safeguard
            message_queue.put({"type": "fatal", "message": f"批量处理线程异常：{exc}"})

    def _poll_processing_queue(self) -> None:
        if self._processing_queue is None:
            return

        should_continue = True
        while True:
            try:
                message = self._processing_queue.get_nowait()
            except queue.Empty:
                break
            should_continue = self._handle_processing_message(message)
            if not should_continue:
                break

        if should_continue and self._is_processing:
            self.root.after(60, self._poll_processing_queue)

    def _handle_processing_message(self, message: dict) -> bool:
        message_type = message.get("type")
        if message_type == "progress":
            current = int(message.get("current", 0))
            total = max(1, int(message.get("total", 1)))
            filename = str(message.get("filename", ""))
            status_text = str(message.get("status_text", ""))
            self.progress_bar.configure(maximum=total)
            self.progress_value_var.set(current)
            self.progress_text_var.set(f"正在处理 {current} / {total}：{filename}  {status_text}")
            return True

        if message_type == "done":
            self._finish_batch_processing(
                processed_crops=message.get("processed_crops", {}),
                item_updates=message.get("item_updates", {}),
                success_count=int(message.get("success_count", 0)),
                failure_count=int(message.get("failure_count", 0)),
            )
            return False

        if message_type == "fatal":
            self._set_processing_state(False)
            self.progress_text_var.set("批量处理失败")
            self.progress_value_var.set(0)
            self._processing_queue = None
            self._processing_thread = None
            self._processing_completion_callback = None
            self._processing_selected_index = None
            messagebox.showerror("批量处理失败", str(message.get("message", "发生未知错误。")))
            return False

        return True

    def _finish_batch_processing(
        self,
        processed_crops: dict[str, np.ndarray],
        item_updates: dict[str, dict],
        success_count: int,
        failure_count: int,
    ) -> None:
        if self.project is None:
            self._set_processing_state(False)
            self.progress_text_var.set("批量处理已取消")
            self.progress_value_var.set(0)
            self._processing_queue = None
            self._processing_thread = None
            self._processing_completion_callback = None
            self._processing_selected_index = None
            return

        image_map = self.project.image_map()
        for filename, update in item_updates.items():
            item = image_map.get(filename)
            if item is None:
                continue
            item.status = str(update.get("status", item.status))
            item.message = str(update.get("message", item.message))
            if bool(update.get("update_auto_rect")):
                item.auto_rect = update.get("auto_rect")
            if item.status != "success":
                self.log(f"{filename}: {item.message}")

        self.processed_crops = processed_crops
        self.selected_edge = None
        self._refresh_stretch_target_height_from_crops()
        self.refresh_image_list(self._processing_selected_index)
        if self._processing_selected_index is not None:
            self.select_index(self._processing_selected_index)
        else:
            self.refresh_current_image()
        self.refresh_final_preview()
        self.progress_bar.configure(maximum=max(1, success_count + failure_count))
        self.progress_value_var.set(success_count + failure_count)
        self.progress_text_var.set(f"批量处理完成：成功 {success_count} 张，失败 {failure_count} 张")
        self.log(f"批量处理完成，成功 {success_count} 张，失败 {failure_count} 张。")

        callback = self._processing_completion_callback
        self._processing_queue = None
        self._processing_thread = None
        self._processing_completion_callback = None
        self._processing_selected_index = None
        self._set_processing_state(False)

        if callback is not None:
            callback()

    def _set_processing_state(self, is_processing: bool) -> None:
        self._is_processing = is_processing
        toolbar_state = "disabled" if is_processing else "normal"
        for button in self.toolbar_buttons.values():
            button.configure(state=toolbar_state)
        if self.project_name_entry is not None:
            self.project_name_entry.configure(state=toolbar_state)
        self._update_export_name_control_state()
        if is_processing:
            self.image_tree.state(["disabled"])
        else:
            self.image_tree.state(["!disabled"])
        self.image_canvas.configure(cursor="watch" if is_processing else "")

    def new_project(self) -> None:
        source_dir = filedialog.askdirectory(title="选择原图文件夹")
        if not source_dir:
            return

        source_path = Path(source_dir)
        files = list_image_files(source_path)
        if not files:
            messagebox.showwarning("没有图片", "所选文件夹中没有可处理的图片文件。")
            return

        self.project = ProjectData(
            project_name=source_path.name,
            source_dir=source_path,
            images=[ImageState(filename=file.name) for file in files],
        )
        self.project_file = None
        self.selected_edge = None
        self.processed_crops.clear()
        self.original_cache.clear()
        self.thumbnail_cache.clear()
        self._load_project_metadata_to_ui()
        self._load_settings_to_ui()
        self.refresh_image_list()
        self.select_index(0)
        self.log(f"已新建项目，读取 {len(files)} 张图片。")

    def open_project(self) -> None:
        file_path = filedialog.askopenfilename(
            title="打开项目",
            filetypes=[("CutImage 项目", "*.cutimage.json"), ("JSON 文件", "*.json")],
        )
        if not file_path:
            return

        try:
            project = load_project(Path(file_path))
        except Exception as exc:
            messagebox.showerror("打开失败", f"无法打开项目文件：{exc}")
            return

        self.project = project
        self.project_file = Path(file_path)
        self.selected_edge = None
        self.processed_crops.clear()
        self.original_cache.clear()
        self.thumbnail_cache.clear()
        self._load_project_metadata_to_ui()
        self._load_settings_to_ui()
        self._restore_processed_crops_from_project()
        self.refresh_image_list()
        if project.images:
            self.select_index(0)
        self.refresh_final_preview()
        self.log(f"已打开项目：{self.project_file.name}")

    def save_project_action(self) -> None:
        if not self.ensure_project():
            return
        self._sync_project_metadata_from_ui()
        self._sync_settings_from_ui()
        assert self.project is not None
        if self.project_file is None:
            self.save_project_as()
            return

        try:
            save_project(self.project, self.project_file)
        except Exception as exc:
            messagebox.showerror("保存失败", f"保存项目失败：{exc}")
            return
        self.log(f"已保存项目：{self.project_file}")

    def save_project_as(self) -> None:
        if not self.ensure_project():
            return
        self._sync_project_metadata_from_ui()
        self._sync_settings_from_ui()
        assert self.project is not None

        file_path = filedialog.asksaveasfilename(
            title="另存项目",
            defaultextension=".cutimage.json",
            initialfile=f"{self.project.project_name or 'project'}.cutimage.json",
            filetypes=[("CutImage 项目", "*.cutimage.json"), ("JSON 文件", "*.json")],
        )
        if not file_path:
            return

        self.project_file = Path(file_path)
        self.save_project_action()

    def process_all_images(self) -> None:
        self._start_batch_processing()

    def export_results(self) -> None:
        if not self.ensure_project():
            return
        if self._is_processing:
            messagebox.showinfo("正在处理", "请等待当前批量处理完成后再导出。")
            return
        if not self.processed_crops:
            self.log("导出前自动启动批量处理。")
            self._start_batch_processing(on_complete=self._export_results_after_processing)
            return

        self._sync_settings_from_ui()
        assert self.project is not None
        self._sync_project_metadata_from_ui()
        base_dir = self._resolve_export_base_dir()
        if base_dir is None:
            return

        cropped_dir = base_dir / "cropped"
        final_dir = base_dir / "final"
        project_dir = base_dir / "project"
        extension = "png"

        for item in self.project.images:
            crop = self.processed_crops.get(item.filename)
            if crop is None:
                continue
            save_rgb_image(self._build_crop_output(crop), cropped_dir / f"{Path(item.filename).stem}.{extension}")

        try:
            final_base_name = self._effective_final_image_name()
            final_output_path = self._next_available_path(final_dir / f"{final_base_name}.{extension}")
            final_image = self._build_final_from_cache(size_mode="original")
            save_rgb_image(final_image, final_output_path)
        except ImageProcessingError as exc:
            messagebox.showerror("导出失败", f"无法生成拼接图：{exc}")
            return

        self.project.output_dir = base_dir
        exported_project_file = project_dir / f"{self.project.project_name}.cutimage.json"
        save_project(self.project, exported_project_file)
        if self.project_file is not None:
            save_project(self.project, self.project_file)

        self.log(f"导出完成：{final_output_path}")
        messagebox.showinfo(
            "导出完成",
            f"结果已导出到：\n{final_output_path}",
        )

    def _export_results_after_processing(self) -> None:
        if not self.processed_crops:
            messagebox.showwarning("无法导出", "批量处理完成后仍没有可导出的结果。")
            return
        self.export_results()

    def move_selected_image(self, direction: int) -> None:
        if self._is_processing:
            self.log("批量处理中，暂时不能调整图片顺序。")
            return
        if not self.ensure_project():
            return
        assert self.project is not None
        index = self.get_selected_index()
        if index is None:
            return
        new_index = index + direction
        if new_index < 0 or new_index >= len(self.project.images):
            return
        self.project.images[index], self.project.images[new_index] = (
            self.project.images[new_index],
            self.project.images[index],
        )
        self.refresh_image_list(new_index)
        self.refresh_current_image()
        self.refresh_final_preview()

    def restore_auto_sort(self) -> None:
        if self._is_processing:
            self.log("批量处理中，暂时不能恢复排序。")
            return
        if not self.ensure_project():
            return
        assert self.project is not None
        self.project.images.sort(key=lambda item: item.filename.lower())
        self.refresh_image_list(0 if self.project.images else None)
        self.refresh_current_image()
        self.refresh_final_preview()
        self.log("已恢复按文件名自动排序。")

    def apply_manual_rect_from_inputs(self) -> None:
        if self._is_processing:
            self.log("批量处理中，暂时不能修改裁剪框。")
            return
        item = self.get_current_image_state()
        if item is None:
            return

        image = self.get_original_image(item.filename)
        if image is None:
            return

        left = self.rect_left_var.get()
        top = self.rect_top_var.get()
        right = self.rect_right_var.get()
        bottom = self.rect_bottom_var.get()
        if right <= left or bottom <= top:
            messagebox.showwarning("参数无效", "右边界必须大于左边界，下边界必须大于上边界。")
            return

        self._apply_manual_rect_update(item, Rect(left, top, right - left, bottom - top), image)
        self.log(f"{item.filename}: 已应用手动修正。")

    def clear_manual_rect(self) -> None:
        if self._is_processing:
            self.log("批量处理中，暂时不能清除手动修正。")
            return
        item = self.get_current_image_state()
        if item is None:
            return
        item.manual_rect = None
        self.selected_edge = None
        self.process_all_images()
        self.log(f"{item.filename}: 已清除手动修正。")

    def on_select_image(self) -> None:
        if self._suppress_select_image_reset:
            return
        self.selected_edge = None
        self.refresh_current_image()

    def refresh_current_image(self) -> None:
        item = self.get_current_image_state()
        if item is None:
            self._draw_placeholder()
            return
        self._sync_settings_from_ui()

        image = self.get_original_image(item.filename)
        if image is None:
            self._draw_placeholder()
            return

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        canvas_width = max(200, self.image_canvas.winfo_width())
        canvas_height = max(200, self.image_canvas.winfo_height())
        image_h, image_w = rgb.shape[:2]
        self.display_scale = min(canvas_width / image_w, canvas_height / image_h)
        display_size = (
            max(1, int(image_w * self.display_scale)),
            max(1, int(image_h * self.display_scale)),
        )
        offset_x = (canvas_width - display_size[0]) // 2
        offset_y = (canvas_height - display_size[1]) // 2
        self.display_offset = (offset_x, offset_y)

        self.current_image_photo = ImageTk.PhotoImage(to_pil_image(rgb).resize(display_size))
        self.image_canvas.delete("all")
        self.image_canvas.create_image(offset_x, offset_y, anchor=tk.NW, image=self.current_image_photo)

        rect = item.effective_rect
        if rect:
            self._draw_rect_on_canvas(rect)
            self._set_rect_inputs(rect)
            self._show_crop_preview(image, rect)
        else:
            self.selected_edge = None
            self._clear_crop_preview()

    def refresh_previews(self, *_args) -> None:
        self.refresh_current_image()
        self.refresh_final_preview()

    def refresh_final_preview(self, *_args) -> None:
        if not self.processed_crops or self.project is None:
            self.final_preview_label.configure(image="", text="暂无拼接预览")
            self.final_preview_photo = None
            return

        self._sync_settings_from_ui()
        try:
            final_rgb = self._build_final_from_cache(size_mode="target_height")
        except ImageProcessingError as exc:
            self.final_preview_label.configure(image="", text=str(exc))
            self.final_preview_photo = None
            return

        preview = to_pil_image(final_rgb)
        preview.thumbnail((520, 280))
        self.final_preview_photo = ImageTk.PhotoImage(preview)
        self.final_preview_label.configure(image=self.final_preview_photo, text="")

    def refresh_image_list(self, selected_index: int | None = None) -> None:
        self._suppress_select_image_reset = True
        self.image_tree.delete(*self.image_tree.get_children())
        if not self.project:
            self._suppress_select_image_reset = False
            return

        for item in self.project.images:
            tags = []
            if item.manual_rect:
                tags.append("手动")
            status_label = STATUS_LABELS.get(item.status)
            if status_label:
                tags.append(status_label)
            label = item.filename if not tags else f"{item.filename} [{' / '.join(tags)}]"
            thumbnail = self._get_list_thumbnail(item.filename)
            item_id = str(len(self.image_tree.get_children()))
            self.image_tree.insert("", tk.END, iid=item_id, text=label, image=thumbnail)

        if selected_index is not None and 0 <= selected_index < len(self.project.images):
            item_id = str(selected_index)
            self.image_tree.selection_set(item_id)
            self.image_tree.focus(item_id)
            self.image_tree.see(item_id)
        self._suppress_select_image_reset = False

    def select_index(self, index: int | None) -> None:
        self.image_tree.selection_remove(self.image_tree.selection())
        if index is None:
            return
        item_id = str(index)
        self.image_tree.selection_set(item_id)
        self.image_tree.focus(item_id)
        self.image_tree.see(item_id)
        self.refresh_current_image()

    def on_canvas_press(self, event: tk.Event) -> None:
        if self._is_processing:
            return
        self.image_canvas.focus_set()
        item = self.get_current_image_state()
        if item is None:
            return

        image = self.get_original_image(item.filename)
        if image is None:
            return

        rect = item.effective_rect
        point = self._canvas_to_image_coords(event.x, event.y, image.shape[1], image.shape[0])
        if point is None:
            return

        if rect:
            mode = self._hit_test_rect(rect, event.x, event.y)
            if mode:
                if mode in {"left", "top", "right", "bottom"}:
                    self.selected_edge = mode
                    self.drag_mode = None
                    self.drag_anchor = None
                    self.drag_start_rect = None
                    self.refresh_current_image()
                    return
                self.selected_edge = None
                self.drag_mode = mode
                self.drag_anchor = point
                self.drag_start_rect = Rect(rect.x, rect.y, rect.width, rect.height)
                return

        self.selected_edge = None
        self.refresh_current_image()
        self.drag_mode = "create"
        self.drag_anchor = point
        self.drag_start_rect = Rect(point[0], point[1], 1, 1)

    def on_canvas_drag(self, event: tk.Event) -> None:
        if self._is_processing:
            return
        item = self.get_current_image_state()
        if item is None or self.drag_mode is None or self.drag_anchor is None or self.drag_start_rect is None:
            return

        image = self.get_original_image(item.filename)
        if image is None:
            return

        point = self._canvas_to_image_coords(
            event.x,
            event.y,
            image.shape[1],
            image.shape[0],
            clamp=True,
        )
        if point is None:
            return

        self._apply_manual_rect_update(
            item,
            self._rect_from_drag(self.drag_mode, self.drag_start_rect, self.drag_anchor, point),
            image,
        )

    def on_canvas_release(self, _event: tk.Event) -> None:
        if self._is_processing:
            return
        if self.drag_mode is None:
            return
        self.refresh_image_list(self.get_selected_index())
        self.drag_mode = None
        self.drag_anchor = None
        self.drag_start_rect = None
        self.image_canvas.focus_set()

    def on_canvas_key_press(self, event: tk.Event) -> str | None:
        if self._is_processing or self.selected_edge is None:
            return None

        item = self.get_current_image_state()
        if item is None:
            return None

        image = self.get_original_image(item.filename)
        rect = item.effective_rect
        if image is None or rect is None:
            return None

        step = 5 if bool(event.state & 0x0001) else 1
        new_rect = self._rect_after_edge_nudge(rect, self.selected_edge, event.keysym, step)
        if new_rect is None:
            return None

        self._apply_manual_rect_update(item, new_rect, image)
        self.image_canvas.focus_set()
        self.refresh_current_image()
        return "break"

    def get_selected_index(self) -> int | None:
        selection = self.image_tree.selection()
        if not selection:
            return None
        return int(selection[0])

    def get_current_image_state(self) -> ImageState | None:
        if not self.project:
            return None
        index = self.get_selected_index()
        if index is None or index >= len(self.project.images):
            return None
        return self.project.images[index]

    def get_original_image(self, filename: str) -> np.ndarray | None:
        if filename in self.original_cache:
            return self.original_cache[filename]
        if not self.project:
            return None

        image_path = self.project.source_dir / filename
        try:
            image = read_image(image_path)
        except ImageProcessingError as exc:
            self.log(str(exc))
            return None

        self.original_cache[filename] = image
        return image

    def _get_list_thumbnail(self, filename: str) -> ImageTk.PhotoImage:
        cached = self.thumbnail_cache.get(filename)
        if cached is not None:
            return cached

        image = self.get_original_image(filename)
        canvas_size = (72, 96)
        background = Image.new("RGB", canvas_size, "#101010")

        if image is not None:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            thumbnail = Image.fromarray(rgb)
            thumbnail.thumbnail(canvas_size)
            offset_x = (canvas_size[0] - thumbnail.width) // 2
            offset_y = (canvas_size[1] - thumbnail.height) // 2
            background.paste(thumbnail, (offset_x, offset_y))

        photo = ImageTk.PhotoImage(background)
        self.thumbnail_cache[filename] = photo
        return photo

    def ensure_project(self) -> bool:
        if self.project is None:
            messagebox.showwarning("没有项目", "请先新建项目或打开已有项目。")
            return False
        return True

    def _resolve_export_base_dir(self) -> Path | None:
        assert self.project is not None
        if self.project.output_dir is not None:
            return self.project.output_dir

        output_dir = filedialog.askdirectory(title="选择导出目录")
        if not output_dir:
            return None
        return Path(output_dir) / self.project.project_name

    def _effective_final_image_name(self) -> str:
        assert self.project is not None
        if self.project.final_image_name_sync_with_project:
            preferred_name = self.project.project_name
        else:
            preferred_name = self.project.final_image_name or self.project.project_name

        sanitized_name = self._sanitize_filename_stem(preferred_name)
        if sanitized_name:
            return sanitized_name

        fallback_name = self._sanitize_filename_stem(self.project.project_name)
        if fallback_name:
            return fallback_name

        return "combined_result"

    def _sanitize_filename_stem(self, value: str) -> str:
        sanitized = str(value).strip()
        for char in INVALID_FILENAME_CHARS:
            sanitized = sanitized.replace(char, "_")
        sanitized = sanitized.strip().rstrip(". ")
        return sanitized

    def _next_available_path(self, path: Path) -> Path:
        if not path.exists():
            return path

        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        index = 1
        while True:
            candidate = parent / f"{stem}_{index:03d}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

    def log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _load_settings_to_ui(self) -> None:
        if not self.project:
            return

        settings = self.project.settings
        self.threshold_var.set(settings.threshold)
        self.padding_var.set(settings.padding)
        self.spacing_var.set(settings.spacing)
        self.target_height_var.set(settings.target_height)
        self.stretch_target_height_var.set(settings.stretch_target_height)
        self.background_mode_var.set(self._background_label(settings.background_mode))
        self.align_mode_var.set(self._align_label(settings.align_mode))
        self.output_format_var.set("png")
        self.add_outline_var.set(settings.add_outline_on_white)
        self.crop_shape_mode_var.set(self._shape_label(settings.crop_shape_mode))
        self.crop_corner_radius_var.set(settings.crop_corner_radius)
        self.final_shape_mode_var.set(self._shape_label(settings.final_shape_mode))
        self.final_corner_radius_var.set(settings.final_corner_radius)
        self._update_control_state()

    def _load_project_metadata_to_ui(self) -> None:
        if not self.project:
            return

        self.project_name_var.set(self.project.project_name)
        self.final_image_name_var.set(self.project.final_image_name)
        self.final_image_name_sync_var.set(self.project.final_image_name_sync_with_project)
        self._update_export_name_control_state()

    def _sync_project_metadata_from_ui(self) -> None:
        if not self.project:
            return

        project_name = self.project_name_var.get().strip()
        if project_name:
            self.project.project_name = project_name
        self.project.final_image_name = self.final_image_name_var.get().strip()
        self.project.final_image_name_sync_with_project = self.final_image_name_sync_var.get()

    def _sync_settings_from_ui(self) -> None:
        if not self.project:
            return

        self.project.settings = ProcessingSettings(
            threshold=self.threshold_var.get(),
            padding=self.padding_var.get(),
            spacing=self.spacing_var.get(),
            target_height=self.target_height_var.get(),
            stretch_target_height=self.stretch_target_height_var.get(),
            background_mode=BACKGROUND_LABELS.get(self.background_mode_var.get(), "black"),
            output_format="png",
            align_mode=ALIGN_LABELS.get(self.align_mode_var.get(), "center"),
            crop_shape_mode=SHAPE_LABELS.get(self.crop_shape_mode_var.get(), "square"),
            crop_corner_radius=self.crop_corner_radius_var.get(),
            final_shape_mode=SHAPE_LABELS.get(self.final_shape_mode_var.get(), "square"),
            final_corner_radius=self.final_corner_radius_var.get(),
            add_outline_on_white=self.add_outline_var.get(),
        )

    def _background_label(self, mode: str) -> str:
        for label, value in BACKGROUND_LABELS.items():
            if value == mode:
                return label
        return "纯黑"

    def _align_label(self, mode: str) -> str:
        for label, value in ALIGN_LABELS.items():
            if value == mode:
                return label
        return "居中对齐"

    def _shape_label(self, mode: str) -> str:
        for label, value in SHAPE_LABELS.items():
            if value == mode:
                return label
        return "直角矩形"

    def _on_crop_shape_change(self, _event=None) -> None:
        self._update_control_state()
        self.refresh_current_image()

    def _on_final_shape_change(self, _event=None) -> None:
        self._update_control_state()
        self.refresh_final_preview()

    def _on_align_mode_change(self, _event=None) -> None:
        self._update_control_state()
        self.refresh_final_preview()

    def _on_final_image_name_sync_change(self) -> None:
        self._update_export_name_control_state()

    def _update_control_state(self) -> None:
        crop_state = "normal" if SHAPE_LABELS.get(self.crop_shape_mode_var.get(), "square") == "rounded" else "disabled"
        final_state = "normal" if SHAPE_LABELS.get(self.final_shape_mode_var.get(), "square") == "rounded" else "disabled"
        stretch_state = (
            "normal" if ALIGN_LABELS.get(self.align_mode_var.get(), "center") == "stretch" else "disabled"
        )
        self.crop_corner_radius_spinbox.configure(state=crop_state)
        self.final_corner_radius_spinbox.configure(state=final_state)
        self.stretch_target_height_spinbox.configure(state=stretch_state)

    def _update_export_name_control_state(self) -> None:
        entry_state = "disabled" if self._is_processing or self.final_image_name_sync_var.get() else "normal"
        checkbutton_state = "disabled" if self._is_processing else "normal"
        if self.final_image_name_entry is not None:
            self.final_image_name_entry.configure(state=entry_state)
        if self.final_image_name_sync_checkbutton is not None:
            self.final_image_name_sync_checkbutton.configure(state=checkbutton_state)

    def _draw_rect_on_canvas(self, rect: Rect) -> None:
        x1, y1 = self._image_to_canvas_coords(rect.x, rect.y)
        x2, y2 = self._image_to_canvas_coords(rect.right, rect.bottom)
        self.image_canvas.create_rectangle(x1, y1, x2, y2, outline="#00d084", width=2)
        if self.selected_edge is not None:
            self._draw_selected_edge_highlight(x1, y1, x2, y2, self.selected_edge)
        for handle_x, handle_y in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
            self.image_canvas.create_oval(
                handle_x - self.HANDLE_RADIUS,
                handle_y - self.HANDLE_RADIUS,
                handle_x + self.HANDLE_RADIUS,
                handle_y + self.HANDLE_RADIUS,
                fill="#00d084",
                outline="white",
            )

    def _show_crop_preview(self, image_bgr: np.ndarray, rect: Rect) -> None:
        try:
            crop_rgb = crop_image(image_bgr, rect)
        except ImageProcessingError:
            self._clear_crop_preview()
            return
        preview = to_pil_image(self._build_crop_output(crop_rgb))
        preview.thumbnail((500, 280))
        self.current_crop_photo = ImageTk.PhotoImage(preview)
        self.crop_preview_label.configure(image=self.current_crop_photo, text="")

    def _clear_crop_preview(self) -> None:
        self.crop_preview_label.configure(image="", text="暂无裁剪预览")
        self.current_crop_photo = None

    def _draw_placeholder(self) -> None:
        self.selected_edge = None
        self.image_canvas.delete("all")
        width = max(200, self.image_canvas.winfo_width())
        height = max(200, self.image_canvas.winfo_height())
        self.image_canvas.create_text(
            width // 2,
            height // 2,
            text="选择项目并导入图片后开始处理",
            fill="#cccccc",
            font=("Microsoft YaHei UI", 15),
        )
        self._clear_crop_preview()
        self.final_preview_label.configure(image="", text="暂无拼接预览")
        self.final_preview_photo = None

    def _set_rect_inputs(self, rect: Rect) -> None:
        self.rect_left_var.set(rect.x)
        self.rect_top_var.set(rect.y)
        self.rect_right_var.set(rect.right)
        self.rect_bottom_var.set(rect.bottom)

    def _update_current_image_list_item(self) -> None:
        if self.project is None:
            return
        index = self.get_selected_index()
        if index is None or index >= len(self.project.images):
            return

        item = self.project.images[index]
        tags = []
        if item.manual_rect:
            tags.append("手动")
        status_label = STATUS_LABELS.get(item.status)
        if status_label:
            tags.append(status_label)
        label = item.filename if not tags else f"{item.filename} [{' / '.join(tags)}]"
        item_id = str(index)
        if self.image_tree.exists(item_id):
            self.image_tree.item(item_id, text=label, image=self._get_list_thumbnail(item.filename))

    def _update_processed_crop_for_item(self, item: ImageState) -> None:
        image = self.get_original_image(item.filename)
        rect = item.effective_rect
        if image is None or rect is None:
            self.processed_crops.pop(item.filename, None)
            return
        try:
            self.processed_crops[item.filename] = crop_image(image, rect)
        except ImageProcessingError:
            self.processed_crops.pop(item.filename, None)

    def _restore_processed_crops_from_project(self) -> None:
        if self.project is None:
            return

        self.processed_crops.clear()
        restored_count = 0
        for item in self.project.images:
            before_count = len(self.processed_crops)
            self._update_processed_crop_for_item(item)
            if len(self.processed_crops) > before_count:
                restored_count += 1

        if restored_count > 0:
            self._refresh_stretch_target_height_from_crops()
            self.log(f"已根据保存的裁剪框恢复 {restored_count} 张拼接缓存。")

    def _build_final_from_cache(self, size_mode: str = "target_height") -> np.ndarray:
        assert self.project is not None
        ordered_crops = [
            self.processed_crops[item.filename]
            for item in self.project.images
            if item.filename in self.processed_crops
        ]
        return build_final_image(ordered_crops, self.project.settings, size_mode=size_mode)

    def _refresh_stretch_target_height_from_crops(self) -> None:
        if self.project is None:
            return

        heights = [crop.shape[0] for crop in self.processed_crops.values() if crop is not None and crop.size > 0]
        if not heights:
            return

        average_height = max(1, int((sum(heights) / len(heights)) + 0.5))
        self.project.settings.stretch_target_height = average_height
        self.stretch_target_height_var.set(average_height)

    def _build_crop_output(self, crop_rgb: np.ndarray) -> np.ndarray:
        if self.project is None:
            return crop_rgb
        settings = self.project.settings
        return apply_shape_style(
            crop_rgb,
            settings.crop_shape_mode,
            settings.crop_corner_radius,
            background_rgb_for_mode(settings.background_mode),
        )

    def _image_to_canvas_coords(self, x: int, y: int) -> tuple[int, int]:
        offset_x, offset_y = self.display_offset
        return int(offset_x + x * self.display_scale), int(offset_y + y * self.display_scale)

    def _canvas_to_image_coords(
        self,
        x: int,
        y: int,
        image_width: int,
        image_height: int,
        clamp: bool = False,
    ) -> tuple[int, int] | None:
        offset_x, offset_y = self.display_offset
        rel_x = (x - offset_x) / self.display_scale
        rel_y = (y - offset_y) / self.display_scale
        if clamp:
            rel_x = min(max(rel_x, 0), image_width - 1)
            rel_y = min(max(rel_y, 0), image_height - 1)
        if rel_x < 0 or rel_y < 0 or rel_x >= image_width or rel_y >= image_height:
            return None
        return int(rel_x), int(rel_y)

    def _hit_test_rect(self, rect: Rect, canvas_x: int, canvas_y: int) -> str | None:
        x1, y1 = self._image_to_canvas_coords(rect.x, rect.y)
        x2, y2 = self._image_to_canvas_coords(rect.right, rect.bottom)
        points = {
            "nw": (x1, y1),
            "ne": (x2, y1),
            "sw": (x1, y2),
            "se": (x2, y2),
        }
        for name, (px, py) in points.items():
            if abs(canvas_x - px) <= self.HANDLE_RADIUS * 2 and abs(canvas_y - py) <= self.HANDLE_RADIUS * 2:
                return name
        edge_hit = self.EDGE_HIT_WIDTH
        if y1 + self.HANDLE_RADIUS <= canvas_y <= y2 - self.HANDLE_RADIUS:
            if abs(canvas_x - x1) <= edge_hit:
                return "left"
            if abs(canvas_x - x2) <= edge_hit:
                return "right"
        if x1 + self.HANDLE_RADIUS <= canvas_x <= x2 - self.HANDLE_RADIUS:
            if abs(canvas_y - y1) <= edge_hit:
                return "top"
            if abs(canvas_y - y2) <= edge_hit:
                return "bottom"
        if x1 <= canvas_x <= x2 and y1 <= canvas_y <= y2:
            return "move"
        return None

    def _rect_from_drag(
        self,
        mode: str,
        start_rect: Rect,
        anchor: tuple[int, int],
        point: tuple[int, int],
    ) -> Rect:
        left = start_rect.x
        top = start_rect.y
        right = start_rect.right
        bottom = start_rect.bottom

        if mode == "move":
            dx = point[0] - anchor[0]
            dy = point[1] - anchor[1]
            return Rect(left + dx, top + dy, start_rect.width, start_rect.height)
        if mode == "create":
            new_left = min(anchor[0], point[0])
            new_top = min(anchor[1], point[1])
            new_right = max(anchor[0], point[0])
            new_bottom = max(anchor[1], point[1])
            return Rect(new_left, new_top, max(1, new_right - new_left), max(1, new_bottom - new_top))
        if mode == "nw":
            left, top = point
        elif mode == "ne":
            right, top = point
        elif mode == "sw":
            left, bottom = point
        elif mode == "se":
            right, bottom = point

        if right <= left:
            right = left + 1
        if bottom <= top:
            bottom = top + 1
        return Rect(left, top, right - left, bottom - top)

    def _draw_selected_edge_highlight(self, x1: int, y1: int, x2: int, y2: int, edge: str) -> None:
        if edge == "left":
            coords = (x1, y1, x1, y2)
        elif edge == "top":
            coords = (x1, y1, x2, y1)
        elif edge == "right":
            coords = (x2, y1, x2, y2)
        elif edge == "bottom":
            coords = (x1, y2, x2, y2)
        else:
            return
        self.image_canvas.create_line(*coords, fill="#ffd166", width=4)

    def _apply_manual_rect_update(self, item: ImageState, rect: Rect, image: np.ndarray) -> None:
        item.manual_rect = rect.clamp(image.shape[1], image.shape[0])
        item.status = "success"
        item.message = "手动修正"
        self._update_current_image_list_item()
        self.refresh_current_image()
        self._update_processed_crop_for_item(item)
        self._refresh_stretch_target_height_from_crops()
        self.refresh_final_preview()

    def _rect_after_edge_nudge(self, rect: Rect, edge: str, keysym: str, step: int) -> Rect | None:
        left = rect.x
        top = rect.y
        right = rect.right
        bottom = rect.bottom

        if edge in {"left", "right"}:
            if keysym not in {"Left", "Right"}:
                return None
            delta = -step if keysym == "Left" else step
            if edge == "left":
                left += delta
            else:
                right += delta
        elif edge in {"top", "bottom"}:
            if keysym not in {"Up", "Down"}:
                return None
            delta = -step if keysym == "Up" else step
            if edge == "top":
                top += delta
            else:
                bottom += delta
        else:
            return None

        if right <= left:
            if edge == "left":
                left = right - 1
            else:
                right = left + 1
        if bottom <= top:
            if edge == "top":
                top = bottom - 1
            else:
                bottom = top + 1
        return Rect(left, top, right - left, bottom - top)
