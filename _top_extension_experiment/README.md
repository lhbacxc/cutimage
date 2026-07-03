# 比色皿上半部分补齐实验

## 1. 目标

这个目录用于验证“只在实验链路里，为比色皿补齐标准化上半部分”是否可行。

本实验具备以下约束：

1. 不修改 `app.py`
2. 不修改 `run_cutimage.bat`
3. 不接入现有 GUI
4. 不改变现有项目保存与导出逻辑
5. 删除 `_top_extension_experiment/` 后，实验能力整体消失

## 2. 目录说明

- `config.json`
  实验配置
- `experiment_runner.py`
  独立实验入口
- `top_extension_renderer.py`
  顶部模板补齐逻辑
- `sample_input/`
  可选的实验输入样例目录
- `sample_output/`
  实验输出目录
- `debug_output/`
  调试对比图目录

## 3. 默认输入

默认配置直接读取项目中的原始图片目录：

- `../image`

如需切换到单独样例目录，可修改 `config.json` 中的 `input_dir`。

## 4. 运行方式

如果你希望像主程序一样直接双击启动 GUI，请使用：

- `run_top_extension_experiment_gui.bat`

这个 GUI 只负责运行实验脚本和查看输出目录，不会改动主程序。

也可以继续使用命令行方式：

推荐使用项目当前约定的 Python 环境运行：

```powershell
D:/Software/Miniconda/envs/cutimage/python.exe ./_top_extension_experiment/experiment_runner.py
```

如果要指定其他配置文件：

```powershell
D:/Software/Miniconda/envs/cutimage/python.exe ./_top_extension_experiment/experiment_runner.py --config ./_top_extension_experiment/config.json
```

## 5. 主要输出

运行后会生成：

1. `sample_output/cropped_original/`
   原始裁剪结果
2. `sample_output/cropped_extended/`
   顶部补齐后的单张结果
3. `sample_output/final_original.png`
   原始拼接图
4. `sample_output/final_extended.png`
   补齐后拼接图
5. `debug_output/`
   单张与拼接的对比图

## 6. 当前方案说明

当前实验使用的是“模板式补齐”：

1. 保留真实下半部分
2. 在顶部画出标准化比色皿头部
3. 用少量参数控制顶部高度、内弧深度、侧壁宽度和融合高度
4. 通过渐变融合降低拼接边界感

这条路线追求的是“看起来更完整”，而不是恢复每张图真实缺失的细节。
