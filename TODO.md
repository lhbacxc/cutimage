# TODO
- 使用鼠标进行拖动和进行扩大或者缩小选框时，总是感觉卡卡的





# Done
- ✅单图修正的时候，可以进行微调
    选中边高亮后可进行微调，按方向键每次微调 1px ，按 Shift + 方向键 每次微调 5px

- ✅双击根目录 `run_cutimage.bat` 时曾额外弹出 `cmd` 窗口，现已改为只启动程序

    原因：`.bat` 文件本身需要由 `cmd.exe` 执行；早期启动器先调用 `python.exe`，后续即使改成 `pythonw.exe`，批处理默认仍会等待子进程结束，所以 `cmd` 窗口还是会跟着保留到 GUI 退出。

    最终修正：将启动器改为使用 `start` 拉起 `pythonw.exe`，让批处理在启动 GUI 后立即结束。当前 `run_cutimage.bat` 的有效形式为：

    `start "" "D:\Software\Miniconda\envs\cutimage\pythonw.exe" "%SCRIPT_DIR%app.py"`

- ✅现在的保存项目是保存为三个文件夹，分别是 cropped、project、final，优化为保存为一个 cropped 文件夹，project 中的配置文件和 final 中最终拼接的图片文件都保存在根目录即可，并且可以勾选是否保存 cropped 文件夹，因为有的时候我并不需要 cropped 文件夹，比如我只需要拼接图片，不需要保存裁剪后的图片。
    已经更改。

- ✅将总文档进行分拆成多个文件+按需引用，并添加更新合并规则文件，这样以后就可以直接让 AI 按照这份规则进行更新合并到相应文件
    以后只需要：
    先阅读 ./AIREADME.md。
    如果本次改动完成后需要同步维护文档，请按 ./docs/project/doc-maintenance.md 更新对应文件。
