# CutImage AI 快速入口

## 项目一句话说明

CutImage 是一个基于 `Tkinter + OpenCV + Pillow + NumPy` 的本地桌面工具，用于批量识别、裁剪并拼接比色皿图片。

## 建议先看

1. 用户入口：`./README.md`
2. 文档导航：`./docs/project/index.md`
3. 运行与启动：`./docs/project/runtime-and-launch.md`
4. 导出规则：`./docs/project/features/export.md`

## 核心入口

1. 启动器：`./run_cutimage.bat`
2. 程序入口：`./app.py`

## 核心代码

1. `./core/models.py`
2. `./core/image_processor.py`
3. `./core/project_store.py`
4. `./ui/main_window.py`

## 当前关键规则

1. 支持中文路径、中文文件名和中文项目文件。
2. 最终拼接图当前只导出一张无损 `png`。
3. 最终图默认增量命名，不覆盖旧文件。
4. 顶部可勾选是否导出 `cropped/` 裁剪图目录。
5. 打开项目后会根据保存的裁剪框恢复缓存与拼接预览。
6. 批量处理在后台线程执行，处理中会禁用冲突操作。
7. 单图修正支持拖拽、手动输入边界、点击边后键盘微调。
8. 拉伸模式下会使用平均高度策略自动更新统一高度。
9. 保存项目时，会保存项目文件，并以当前项目名新建同名文件夹同步输出最终拼接图。

## 遇到问题时看哪里

1. 启动、环境、批处理启动器：`./docs/project/runtime-and-launch.md`
2. 项目目标与能力总览：`./docs/project/overview.md`
3. 项目保存、相对路径、恢复逻辑：`./docs/project/project-file.md`
4. 导出目录、命名、`png` 限制：`./docs/project/features/export.md`
5. 拖拽修框、手动输入、键盘微调：`./docs/project/features/editing.md`

## 不建议再做的事

1. 不要默认先通读 `./docs/project/` 下的全部文档。
2. 先读本文件，再按 `./docs/project/index.md` 跳转到专题文档会更高效。
