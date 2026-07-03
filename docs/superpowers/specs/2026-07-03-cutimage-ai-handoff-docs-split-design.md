# CutImage AI 交接文档拆分与按需查找设计文档

## 1. 背景

当前项目使用 `./项目总览与AI交接文档.md` 作为总览、交接、行为规则和功能现状的统一入口。

这种方式在项目早期是高效的，但随着功能增加，单文件逐渐变长，开始出现以下问题：

1. 新开窗口的 AI 每次都需要先读取整篇文档，首轮上下文成本偏高。
2. 用户提问常常只涉及某一个专题，但 AI 仍会读取大量无关内容。
3. 当前行为、历史演进、设计原因混在一起，不利于快速定位“现在到底怎么工作”。
4. 后续继续维护时，单文件更容易演变为大而全说明书，修改局部规则时也更容易遗漏。

因此需要把现有交接文档从“单一总文档”调整为“短入口 + 导航页 + 专题文档”的结构，以支持按需查找。

## 2. 目标

本次设计目标如下：

1. 降低新开窗口 AI 的首读成本。
2. 让不同问题可以直接跳到对应专题文档，而不是总是通读全量说明。
3. 把“当前行为规则”的唯一真源固定到少量专题文档中，减少重复描述。
4. 保留一个足够短的 AI 快速入口，方便每次交接时优先阅读。
5. 保留现有 `./README.md` 的用户向定位，不把用户文档重新写成开发手册。

## 3. 非目标

本次不处理以下内容：

1. 不修改程序代码逻辑。
2. 不改动已有设计文档的历史内容与命名方式。
3. 不要求一次性把全部旧文档完全重写。
4. 不把专题文档拆得过细，避免形成新的碎片化问题。

## 4. 总体方案

采用三层结构：

1. 用户层：`./README.md`
2. AI / 接手层：`./docs/project/ai-quickstart.md`、`./docs/project/index.md`
3. 专题层：`./docs/project/*.md` 与 `./docs/project/features/*.md`

设计原则如下：

1. `./README.md` 只服务普通使用者。
2. `./docs/project/ai-quickstart.md` 只负责让 AI 快速进入状态，必须保持短。
3. `./docs/project/index.md` 只做导航，不承载规则正文。
4. 每类详细规则只能在一个主文件中展开，其他文件只做摘要和跳转。
5. 当前现状与历史演进分离，避免 AI 把旧行为误判为当前行为。

## 5. 推荐目录结构

推荐新增或逐步形成如下结构：

```text
./README.md
./docs/project/index.md
./docs/project/ai-quickstart.md
./docs/project/overview.md
./docs/project/runtime-and-launch.md
./docs/project/architecture.md
./docs/project/project-file.md
./docs/project/known-issues.md
./docs/project/features/export.md
./docs/project/features/editing.md
./docs/project/features/stretch-mode.md
./docs/project/features/ui-behavior.md
```

如需保留历史演进，可额外新增：

1. `./docs/project/history.md`

## 6. 文件职责

### 6.1 入口文件

`./docs/project/ai-quickstart.md`：

1. 给新开窗口的 AI 首读。
2. 只保留项目一句话说明、启动入口、核心代码位置、当前关键规则、跳转路径。
3. 不写大段历史，不展开专题细节。

`./docs/project/index.md`：

1. 作为文档导航页。
2. 告诉读者“遇到什么问题应该看哪个文件”。
3. 不复述具体规则正文。

### 6.2 总览文件

`./docs/project/overview.md`：

1. 说明项目目标、产品定位、当前主要能力。
2. 适合回答“这个项目现在大概能做什么”。

`./docs/project/runtime-and-launch.md`：

1. 说明运行方式、Conda 环境约束、`./run_cutimage.bat`、`./app.py`。
2. 记录 Windows 启动器为何使用 `pythonw.exe` 与 `start`。

`./docs/project/architecture.md`：

1. 说明 `./app.py`、`./core/`、`./ui/` 的职责边界。
2. 记录关键实现约束，例如中文路径读取策略。

`./docs/project/project-file.md`：

1. 说明项目文件保存哪些内容。
2. 说明 `source_dir`、`output_dir` 的路径策略。
3. 说明打开项目后的恢复逻辑。

`./docs/project/known-issues.md`：

1. 记录当前限制与后续优化方向。
2. 不和“已实现能力”混写。

### 6.3 专题文件

`./docs/project/features/export.md`：

1. 作为导出行为规则的唯一真源。
2. 负责最终图命名、增量导出、目录结构、`cropped/` 开关、`png` 限制。

`./docs/project/features/editing.md`：

1. 负责拖拽修框、手动输入边界、点击边后键盘微调。

`./docs/project/features/stretch-mode.md`：

1. 负责拉伸模式、统一高度与平均高度策略。

`./docs/project/features/ui-behavior.md`：

1. 负责异步批量处理、进度条、处理中禁用操作、未保存提示等界面行为。

## 7. 现有总览文档迁移映射

现有 `./项目总览与AI交接文档.md` 建议按以下方式拆分：

1. “项目目标” -> `./docs/project/overview.md`
2. “当前运行方式” -> `./docs/project/runtime-and-launch.md`
3. “当前目录结构说明” -> `./docs/project/architecture.md`
4. “当前已实现的功能” -> 拆分到 `./docs/project/overview.md` 与 `./docs/project/features/*.md`
5. “当前重要行为规则” -> 分流到 `./docs/project/runtime-and-launch.md`、`./docs/project/project-file.md`、`./docs/project/features/*.md`
6. “当前 GUI 主要界面结构” -> `./docs/project/features/ui-behavior.md`
7. “当前核心实现说明” -> `./docs/project/architecture.md`
8. “阶段性演进” -> `./docs/project/history.md` 或保留为附录
9. “已明确验证过的能力” -> 并入对应专题文档末尾
10. “当前已知限制与后续可优化点” -> `./docs/project/known-issues.md`
11. “交接给新的 AI 的重点” -> `./docs/project/ai-quickstart.md`
12. “最简交接结论” -> `./docs/project/ai-quickstart.md` 开头摘要

## 8. 推荐阅读顺序

后续新开窗口时，推荐让 AI 按以下顺序阅读：

1. `./README.md`
2. `./docs/project/ai-quickstart.md`
3. `./docs/project/index.md`
4. 再根据问题类型阅读对应专题文档

这样可以避免每次都先读完整总览文档。

## 9. 迁移策略

建议分阶段推进，而不是一次性大搬家。

### 9.1 第一阶段

先创建以下高价值文件：

1. `./docs/project/index.md`
2. `./docs/project/ai-quickstart.md`
3. `./docs/project/runtime-and-launch.md`
4. `./docs/project/project-file.md`
5. `./docs/project/features/export.md`
6. `./docs/project/features/editing.md`

这批文件已经能覆盖多数高频问题。

### 9.2 第二阶段

继续补齐：

1. `./docs/project/overview.md`
2. `./docs/project/architecture.md`
3. `./docs/project/features/stretch-mode.md`
4. `./docs/project/features/ui-behavior.md`
5. `./docs/project/known-issues.md`

### 9.3 第三阶段

将 `./项目总览与AI交接文档.md` 降级为迁移入口页：

1. 说明文档已拆分。
2. 给出新的阅读顺序。
3. 提供新目录跳转。
4. 如有需要，仅保留少量历史摘要。

## 10. 维护规则

为了避免拆完后重新膨胀为新的大杂烩，建议固定以下规则：

1. 每条详细规则只能有一个主文件。
2. `./docs/project/ai-quickstart.md` 只写结论，不展开细节。
3. `./docs/project/index.md` 只导航，不承载正文。
4. 当前现状与历史演进必须分开维护。
5. 新功能上线后，优先更新对应专题文档，而不是只补到总览里。

## 11. 优缺点分析

### 11.1 优点

1. AI 首读成本显著下降。
2. 更适合按问题定向查找。
3. 单类规则更容易维护，减少重复和漂移。
4. 后续扩展时不必继续拉长一个总文件。

### 11.2 代价

1. 初次拆分需要整理边界。
2. 需要维护导航页与专题真源的对应关系。
3. 如果纪律不够，仍可能出现多处重复描述。

## 12. 成功标准

如果后续实际落地，至少应达到以下结果：

1. 新开窗口时，AI 不再默认先读整篇 `./项目总览与AI交接文档.md`。
2. 常见问题可以直接根据 `./docs/project/index.md` 跳转到专题文档。
3. 导出、修框、项目恢复等高频规则有明确的单一主文档。
4. 旧总览文档不再承担全部职责，而是退居迁移入口或历史汇总。

## 13. 结论

对当前 CutImage 项目而言，把单一的 AI 交接总文档调整为“用户入口 + AI 快速入口 + 导航页 + 少量专题文档”的分层结构，是可行且值得做的。

这套方案比继续维护单一大文件更适合当前使用方式，也比一次拆成大量碎片文件更平衡。建议按阶段逐步迁移，优先解决 AI 首读成本和高频问题查找效率这两个最直接的痛点。
