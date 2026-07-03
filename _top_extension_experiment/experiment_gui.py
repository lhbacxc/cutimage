from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from experiment_runner import ROOT_DIR, run_experiment


class TopExtensionExperimentApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("CutImage 上半部分补齐实验")
        self.root.geometry("860x620")
        self.root.minsize(760, 520)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.config_path_var = tk.StringVar(value=str(ROOT_DIR / "config.json"))
        self.status_var = tk.StringVar(value="就绪")
        self.last_output_dir: Path | None = None
        self.last_debug_dir: Path | None = None

        self._build_layout()
        self.root.after(120, self._pump_logs)

    def run(self) -> None:
        self.root.mainloop()

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        intro = ttk.Label(
            container,
            text="这个 GUI 只用于运行独立实验，不会改动主程序的入口、项目保存和导出流程。",
            wraplength=780,
        )
        intro.pack(anchor=tk.W)

        config_frame = ttk.LabelFrame(container, text="实验配置", padding=10)
        config_frame.pack(fill=tk.X, pady=(12, 10))

        ttk.Label(config_frame, text="配置文件").grid(row=0, column=0, sticky="w")
        config_entry = ttk.Entry(config_frame, textvariable=self.config_path_var)
        config_entry.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        config_frame.columnconfigure(1, weight=1)
        ttk.Button(config_frame, text="打开目录", command=self.open_experiment_folder).grid(row=0, column=2, sticky="ew")

        button_row = ttk.Frame(container)
        button_row.pack(fill=tk.X, pady=(0, 10))
        self.run_button = ttk.Button(button_row, text="运行实验", command=self.start_experiment)
        self.run_button.pack(side=tk.LEFT)
        ttk.Button(button_row, text="打开输出目录", command=self.open_output_folder).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(button_row, text="打开调试目录", command=self.open_debug_folder).pack(side=tk.LEFT, padx=(10, 0))

        status_row = ttk.Frame(container)
        status_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(status_row, text="状态：").pack(side=tk.LEFT)
        ttk.Label(status_row, textvariable=self.status_var).pack(side=tk.LEFT)

        log_frame = ttk.LabelFrame(container, text="运行日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def start_experiment(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return

        config_path = Path(self.config_path_var.get().strip())
        if not config_path.exists():
            messagebox.showerror("配置不存在", f"未找到配置文件：\n{config_path}")
            return

        self._append_log(f"使用配置：{config_path}")
        self.status_var.set("运行中")
        self.run_button.configure(state="disabled")
        self.worker = threading.Thread(target=self._run_experiment_worker, args=(config_path,), daemon=True)
        self.worker.start()

    def _run_experiment_worker(self, config_path: Path) -> None:
        try:
            result = run_experiment(config_path.resolve(), logger=self.log_queue.put)
        except Exception as exc:  # noqa: BLE001
            self.log_queue.put(f"[ERROR] {exc}")
            self.log_queue.put("__FAILED__")
            return

        self.last_output_dir = result["output_dir"] if isinstance(result["output_dir"], Path) else None
        self.last_debug_dir = result["debug_dir"] if isinstance(result["debug_dir"], Path) else None
        self.log_queue.put("__DONE__")

    def open_experiment_folder(self) -> None:
        self._open_path(ROOT_DIR)

    def open_output_folder(self) -> None:
        target = self.last_output_dir or (ROOT_DIR / "sample_output")
        self._open_path(target)

    def open_debug_folder(self) -> None:
        target = self.last_debug_dir or (ROOT_DIR / "debug_output")
        self._open_path(target)

    def _open_path(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def _pump_logs(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if item == "__DONE__":
                self.status_var.set("运行完成")
                self.run_button.configure(state="normal")
                self._append_log("实验运行完成。")
                continue
            if item == "__FAILED__":
                self.status_var.set("运行失败")
                self.run_button.configure(state="normal")
                self._append_log("实验运行失败，请查看上面的错误信息。")
                continue
            self._append_log(item)

        self.root.after(120, self._pump_logs)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)


if __name__ == "__main__":
    TopExtensionExperimentApp().run()
