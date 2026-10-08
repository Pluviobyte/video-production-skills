# Video Production Skills

这是一个长期维护的 AI 视频制作 skill 精选仓库，用来沉淀我在视频创作、视频复刻、动效生成、片头包装、质检交付等流程中反复使用的方法，也用来把优秀参考视频中的动效拆成 HyperFrames / Remotion 能够实现和复用的组件。

仓库不是只服务于某一个视频项目。后续优秀的视频制作 skill 都会优先收录在这里，并按“视频类型 / 风格 / 工作流环节”持续扩展。当前收录的是 AI 动效导演元 Skill、参考视频复刻质检、暗色 SaaS / AI 产品短片、黑底白字打字开场。

这些 skill 适用于 Codex、Claude Code、Cursor 等支持本地 skill 目录或 Skills CLI 的 AI 编程/创作代理。仓库中的每个一级目录都是一个独立可安装的 skill。

## 长期目标：从复刻到组件库

`reference-video-replica-qc` 的意义不是单纯复制某一个参考视频，而是把参考视频里真正让画面“像视频”的东西拆出来：镜头节奏、入场方式、路径运动、组件状态切换、字幕/标题层级、模型列表、线条轨道、卡片翻转、光效、遮罩、缩放和转场。每一次复刻都应该把这些动效整理成 HyperFrames / Remotion / React / CSS / SVG / GSAP 可以编写、组合和参数化的技术组件。

长期来看，这个仓库会形成一个视频动效组件库。每个通过复刻验证的组件都要留下描述：它适合什么内容、解决什么画面问题、需要哪些输入参数、时间线如何运动、应该用在哪类视频段落、有什么对齐证据和限制。以后 AI 制作视频时，就不只是生成一页页静态版式，而是能够根据脚本内容自由选择这些组件，把开场、解释、列表、对比、流程、CTA、产品展示等段落组合成更接近真实视频语言的成片。

`ai-motion-director` 是这套体系的元导演层：给它一个主题、脚本或简报，它先决定视频的运动隐喻、beat graph、组件调度、素材需求和反 PPT 质检标准，再把任务交给 HyperFrames / Remotion / 生图 / 具体视频 skill 执行。

## 已收录 Skills

| Skill | 视频制作环节 | 适合做什么 | 视频风格 / 方法 | 详情 |
| --- | --- | --- | --- | --- |
| `ai-motion-director`<br>AI 动效导演元 Skill | 主题到动效语言 / 元导演 / 反 PPT 质检 | 给一个主题、脚本或简报，先建立 motion thesis、beat graph、组件/素材计划，再控制 HyperFrames/Remotion 进入制作 | Motion-first：视觉隐喻、连续时间线、状态变化、运动语法、anti-PPT gate | [查看页面](docs/ai-motion-director.md) |
| `reference-video-replica-qc` | 复刻闭环 / 组件沉淀 / 质检 | 参考视频拆解、动效复刻、HyperFrames/Remotion 组件化、五级保真度判定 | 先采样定位、再全帧验收；素材门、运行时门、交付门；MAE/时间偏移/边界帧/PSNR/SSIM/哈希证据 | [查看页面](docs/reference-video-replica-qc.md) |
| `ui-animation-replica`<br>UI 动效复刻 | 参考视频测量与重建 | UI 产品宣传片、开关切换、卡片轮播、标签列表、缩放推镜这类界面动效的代码复刻 | 先分类再分段、逐元素 code-first 决策、亚像素质心测量、五维打分、帧间二阶差分抖动诊断 | [查看页面](docs/ui-animation-replica.md) |
| `dark-saas-magic-video`<br>暗色 SaaS 魔术短片 | 风格化正片生成 | 暗色 SaaS / AI 产品短片、工具发布视频、产品能力展示 | Presenton-like magic UI：黑色空间、底部紫光、动感大字、渐变 CTA、漂浮 UI、模型环、导出物件 | [查看页面](docs/dark-saas-magic-video.md) |
| `black-white-text-opener` | 片头包装 | 新视频片头、教程开场、观点视频开头、产品视频引子 | 纯黑/近黑背景 + 白色大字逐字打出 + 同步 typing click 音效 + 干净转场 | [查看页面](docs/black-white-text-opener.md) |

## 效果预览

### AI 动效导演元 Skill

这是流程控制 skill，暂无单独预览视频；它用于在制作前决定运动隐喻、beat graph、组件调度和反 PPT 质检标准，并控制后续视频 skill 产出成片。

### 黑底白字打字开场

[▶ Watch Black White Text Opener](https://github.com/user-attachments/assets/3962d773-4447-4720-ba59-5e164d0b5ac4)

### 暗色 SaaS / Magic UI

示例成片：**雪踏乌云暗色 SaaS 介绍短片**

[▶ Watch Xuetawuyun Dark SaaS Showcase](https://github.com/user-attachments/assets/6d4236af-6b58-4447-986d-21169ea5e3a6)

### 参考视频复刻闭环

示例成片：**Presenton 复刻 Bitexact 成片**

[▶ Watch Presenton Replica Bitexact Showcase](https://github.com/user-attachments/assets/f792bd12-d8b3-43b7-b751-98aeb033713b)

## 仓库会如何扩展

后续新增的视频制作 skill，会优先按下面几类组织：

- 导演与调度：主题理解、运动隐喻、beat graph、组件选择、素材规划、反 PPT 质检。
- 复刻与组件沉淀：参考视频拆解、时间线还原、动效复刻、HyperFrames/Remotion 组件化、像素级/视觉级对齐、交付检查。
- 片头与包装：黑底白字、标题卡、章节转场、字幕条、CTA 结尾。
- 风格化正片：暗色 SaaS、AI 工具发布、课程预告、观点口播包装、教程动效。
- 素材处理：抽帧、字幕、配音、屏幕录制清理、音画同步。
- 平台适配：抖音、小红书、公众号视频封面/比例/节奏差异。

每个新增 skill 应该同时包含：

- 一个独立 skill 目录，包含 `SKILL.md` 和必要脚本。
- 一个 `docs/<skill-name>.md` 介绍页，说明视频类型、风格、适合/不适合场景。
- 如果 skill 产出可复用动效，要为每个组件写清楚组件描述、适用场景、输入参数、时间线、技术栈、对齐证据和限制。
- 优先提供 MP4 视频预览，放在 `assets/videos/` 或 skill 自己的 `assets/showcases/` 作为可版本化归档。
- README / docs 里的可播放展示使用 GitHub `user-attachments/assets/...` URL，写法参考 Presenton：`[▶ Watch Demo](https://github.com/user-attachments/assets/<id>)`。
- 抽帧图、contact sheet、对照图只作为封面/质检辅助，放在 `assets/images/`。
- 在本 README 的表格中补充一行，说明它属于哪个视频制作环节。

## 推荐安装

先查看仓库内可安装的 skill：

```bash
npx skills add https://github.com/Pluviobyte/video-production-skills --list
```

按需安装单个 skill：

```bash
npx skills add https://github.com/Pluviobyte/video-production-skills --skill ai-motion-director
npx skills add https://github.com/Pluviobyte/video-production-skills --skill reference-video-replica-qc
npx skills add https://github.com/Pluviobyte/video-production-skills --skill ui-animation-replica
npx skills add https://github.com/Pluviobyte/video-production-skills --skill dark-saas-magic-video
npx skills add https://github.com/Pluviobyte/video-production-skills --skill black-white-text-opener
```

## 怎么选择

- 给一个主题、脚本或简报，想让 AI 先做运动隐喻、beat graph、组件调度，并避免 PPT 式视频：用 `ai-motion-director`。
- 要复刻一个已有视频、拆解时间线、把动效沉淀成 HyperFrames/Remotion 组件、验证是否对齐：用 `reference-video-replica-qc`。
- 要照着参考视频把 UI 动效用代码重建出来，需要逐元素测量、逐版打分，或排查"元素有轻微晃动"这类具体问题：用 `ui-animation-replica`。
- 要做暗色科技感 SaaS / AI 产品短片：用 `dark-saas-magic-video`。
- 要给新视频加黑底白字、逐字打字、打字音效开场：用 `black-white-text-opener`。

## 设计边界

- `ai-motion-director` 不替代最终渲染、抽帧、字幕、音频和归档流程；它负责先定义 motion thesis、beat graph、组件/素材计划和 anti-PPT gate。
- `reference-video-replica-qc` 把保真度拆成源码一致、渲染帧像素一致、编码成片帧对齐、视觉对齐、风格对齐五级。任何像素级结论都必须通过素材、运行时和交付三道逐帧门；手写 HyperFrames/Remotion 复刻通常目标是视觉级对齐和参数化组件沉淀。
- `ui-animation-replica` 负责"怎么测量、怎么重建、怎么确认对齐"这一段的执行方法：先分类分段，再逐元素决定 code 还是 crop，用亚像素质心测量几何，用五维度打分确认对齐，用帧间二阶差分诊断抖动。它不做保真度定级（那是 `reference-video-replica-qc` 的职责），也不负责从主题自由创作。
- `dark-saas-magic-video` 是风格级创作 skill，不用于逐帧复刻。
- `black-white-text-opener` 是生成型开场 skill，默认要求逐字打字和同步 typing click 音效；不用于复用原片或声明像素级对齐。

<details>
<summary>English</summary>

# Video Production Skills

This is a long-term AI video production skills library. It is designed to collect reusable skills for video creation, reference recreation, motion design, opener packaging, asset processing, delivery QA, and reusable HyperFrames / Remotion motion components.

The long-term goal is to turn reference-video recreation into a component library. Each aligned motion pattern should become a documented technical component with its use case, inputs, timing contract, implementation stack, evidence, and limitations. Future AI video generation can then select from these components instead of producing static slide-like sequences.

The repository is not limited to the current skills. Future video-production skills should be added here with a dedicated skill directory, a docs page, and preview media when possible.

| Skill | Production Stage | Video Type | Style / Method |
| --- | --- | --- | --- |
| `ai-motion-director` | Topic-to-motion direction / anti-PPT QA | Topic-driven original motion videos, beat graph planning, component routing | Motion-first direction: visual metaphor, state change, motion grammar, asset plan, anti-PPT gate |
| `reference-video-replica-qc` | Recreation loop / component capture / QA | Reference analysis, motion recreation, HyperFrames/Remotion componentization, five-level fidelity classification | Samples locate failures; full frames approve asset, runtime, and delivery gates with MAE, temporal, boundary, PSNR/SSIM, and hash evidence |
| `ui-animation-replica` | Reference measurement / rebuilding / jitter repair | UI promo videos, toggle switches, card carousels, label lists, ending push-ins rebuilt as code animation | Classify then segment; per-element code-first decisions; subpixel centroid measurement; five-dimension scoring; frame-to-frame second-difference jitter diagnosis |
| `dark-saas-magic-video` / Dark SaaS Magic Short | Styled main video | Dark SaaS / AI product shorts | Presenton-like magic UI with black space, purple glow, kinetic type, gradient CTA, floating UI |
| `black-white-text-opener` | Opener packaging | Opening title cards for new videos | Black background, typed white text, timed typing clicks, clean transition |

Recommended install:

```bash
npx skills add https://github.com/Pluviobyte/video-production-skills --list
npx skills add https://github.com/Pluviobyte/video-production-skills --skill ai-motion-director
npx skills add https://github.com/Pluviobyte/video-production-skills --skill reference-video-replica-qc
npx skills add https://github.com/Pluviobyte/video-production-skills --skill ui-animation-replica
npx skills add https://github.com/Pluviobyte/video-production-skills --skill dark-saas-magic-video
npx skills add https://github.com/Pluviobyte/video-production-skills --skill black-white-text-opener
```

These skills are designed for Codex, Claude Code, Cursor, and other agents that support local skills or the Skills CLI.

</details>
