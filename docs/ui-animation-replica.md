# 参考视频复刻闭环

把一支 UI 宣传视频的动效拆成可测量的几何数据，再用 Remotion 的代码把它重建出来，最后用逐帧打分确认对齐。这套 skill 不靠肉眼比对调参数，而是先把每一帧分类、每一段分镜、每一个元素该用代码还是该裁图定下来，再逐元素测量、逐块替换、逐版打分。

它解决的问题是：一个看起来"就是几个 UI 元素在动"的宣传片，手工照着做出来总差一口气——元素位置差一点、节奏差一帧、动起来有轻微晃动，但说不清差在哪里。这套方法把每个模糊的感觉都变成一个可测量的数字，并且每个数字都有对应的修改动作。

## 做什么类型的视频

- UI 产品宣传片、功能展示动画
- 开关切换、卡片轮播、标签列表、卡片放大这类界面动效
- 用 HyperFrames / Remotion 重建已有的参考视频动效
- 已经是代码复刻但"感觉没对齐"的返修定位
- 晃动、抖动、节奏不对这类具体问题的排查

## 长期意义

这个 skill 的重点不只是复刻某一支视频，而是把参考视频里真正让画面像视频的东西拆出来：镜头节奏、入场方式、状态切换、卡片展开、缩放推镜、遮罩和转场。每一次复刻都应该把这些动效整理成能参数化的技术组件——适合什么内容、需要哪些输入、时间线怎么运动、有什么已知限制。

组件积累起来之后，AI 做视频就不只是生成一页页静态版式，而是能根据脚本内容挑组件、组合段落，做出更接近真实视频语言的东西。

## 风格与方法

这是一个方法论 skill，不绑定某种视觉风格。它提供的是一套测量和验证的流程：

- 先分类（图形 / 实拍 / 混合），再决定整体走代码还是部分裁图
- 逐元素决策（code-first, crop-last）：不问"这一段能不能复刻"，只问"这一个元素能不能用代码表达"
- 逐帧测量：背景用网格采样，运动元素用亚像素质心拟合，从不猜模型
- 五维度打分：全局色调、时序对齐、静态区域、动态区域、边缘锐度
- 晃动诊断：比较原片与渲染的帧间二阶差分，把"感觉有点晃"变成具体数值

## 核心约束

这几条是踩坑换来的，skill 执行时会强制遵守：

- **测量方法本身必须被验证**。历史上四种测量方法出过系统性错误：饱和度掩码把半径量小一半、角度算术平均造出虚假常数、固定亮度阈值剖面明暗极性翻转、固定坐标扫描在物体移动后扫到画外。
- **逐帧 MAE 检测不出晃动**。MAE 问的是"这一帧像不像"，晃动是"帧间不均匀"，必须看帧序列的二阶差分。
- **渲染慢速移动的元素必须用 HTML + CSS transform**，且 `will-change: transform` 要和 `transform` 在同一个 DOM 节点上。SVG 文字、SVG 组变换、CSS `left/top` 都会吸附到整像素。
- **全片打分是唯一裁判**。凭感觉改过四次，每次都变差。
- **分层剥离优于继续调参**。不知道该怀疑什么时，把图层一层层剥掉比调阈值有效得多。

## 和其他 skill 的分工

- 主题或脚本出发、自由创作一支动态视频：用 `ai-motion-director`
- 要复刻一支已有视频、并把动效沉淀成组件：用 `reference-video-replica-qc`（拆解与质检）+ `ui-animation-replica`（测量与重建）
- 只做暗色 SaaS / AI 产品风格片：用 `dark-saas-magic-video`
- 只做黑底白字打字开场：用 `black-white-text-opener`

## 安装

```bash
npx skills add https://github.com/Pluviobyte/video-production-skills --skill ui-animation-replica
```

## 目录结构

```text
ui-animation-replica/
├── SKILL.md                      # 八步流程与硬规则
├── agents/openai.yaml            # Codex 侧调用说明
├── scripts/                      # 七个可独立运行的工具
│   ├── classify_frames.py        # 逐帧图形/实拍分类
│   ├── segment_shots.py          # 镜头分段（含兜底）
│   ├── inventory_elements.py     # 逐元素 code/crop 决策
│   ├── measure_background.py     # 背景逐帧网格采样
│   ├── fit_camera_track.py       # 亚像素质心拟合镜头轨
│   ├── score_dimensions.py       # 五维度打分
│   └── diagnose_jitter.py        # 晃动诊断
└── references/
    ├── replica-method.md         # 完整方法论与依据
    ├── remotion-pitfalls.md      # 造成抖动的渲染写法与修复
    ├── measurement-contract.md   # 测量验证与交叉核对规范
    └── scoring-rubric.md         # 五维度怎么读、怎么改
```

## 依赖

```bash
pip install opencv-python numpy
pip install scenedetect[opencv]   # 可选，开启硬切检测
```

需要 `ffmpeg` / `ffprobe` 在 PATH 上，Remotion 通过 `npx remotion` 调用。
