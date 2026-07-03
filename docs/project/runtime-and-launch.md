# 运行与启动

## 当前运行方式

项目当前约定使用本机 Miniconda 中的 `cutimage` 环境运行。

推荐启动方式：

1. 直接双击 `../../run_cutimage.bat`

程序入口文件：

1. `../../app.py`

## 当前启动器行为

`../../run_cutimage.bat` 当前通过 `start` 拉起 `pythonw.exe`，再由 `pythonw.exe` 执行 `app.py`。

这样做的目标是：

1. 双击批处理后不长期保留额外的 `cmd` 窗口。
2. 让启动器只负责拉起 GUI，随后立即结束。

## 为什么不是直接用 `python.exe`

如果批处理里直接调用 `python.exe`，或者即便改成 `pythonw.exe` 但不使用 `start`：

1. `.bat` 仍然会由 `cmd.exe` 执行。
2. `cmd` 默认会等待子进程结束。
3. 黑色控制台窗口会一直保留到 GUI 退出。

当前方案正是为了解决这个问题。

## 当前入口代码

1. `../../app.py` 负责创建并运行 `CutImageApp`
2. `../../ui/main_window.py` 负责主界面逻辑

## 环境约束

当前项目约定中有一条重要规则：

1. 不要在脚本或程序里依赖 `conda activate`
2. 需要直接使用目标环境的 Python 绝对路径

当前启动器已经按这个方式工作。

## 相关代码

1. `../../run_cutimage.bat`
2. `../../app.py`
3. `../../ui/main_window.py`
