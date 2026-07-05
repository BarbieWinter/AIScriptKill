# Sonnet 5 前端实现任务书

> **你的任务**：基于现有项目骨架和本文档，实现 AI 沉浸式悬疑互动剧的完整前端。
> **核心理念**：玩家打开的是一部"互动电影"，不是聊天软件。每一帧画面、每一次交互都要强化沉浸感。
> **关键约束**：支持手机端、复用开源库不做轮子、交互必须惊艳不输文字游戏。

---

## 一、前置准备

### 1.1 必须阅读的文档
- `docs/FRONTEND_EXPERIENCE_DESIGN.md` — 完整交互设计（含 wireframe）
- `docs/API_REFERENCE.md` — 前后端 API 契约
- 本文档 — 设计决策和实现指引

### 1.2 已有骨架文件（不要删除，在此基础上实现）

```
apps/web/app/
├── layout.tsx           # 根布局
├── globals.css          # CSS 变量 + 动画关键帧（可扩展）
├── page.tsx             # 重定向到 /library
├── library/page.tsx     # 剧本库（骨架，需重写）
├── library/[id]/page.tsx  # 剧本详情（骨架，需重写）
├── play/[sessionId]/select/page.tsx  # 角色选择（骨架，需重写）
├── play/[sessionId]/page.tsx         # 游戏主界面（骨架，需重写）
├── play/[sessionId]/review/page.tsx  # 复盘页（骨架，需重写）

apps/web/lib/
├── utils.ts       # cn() 工具函数（已可用）
├── api.ts         # API 客户端（已实现）
├── ws.ts          # WebSocket 客户端（已实现）

apps/web/stores/
├── gameStore.ts   # Zustand 状态管理（已实现，必须使用）

apps/web/types/
├── index.ts       # 类型定义
```

### 1.3 已安装的依赖

```
next ^15          → 框架（App Router）
react ^19         → UI 库
zustand ^5        → 状态管理（必须用，不要换）
@tanstack/react-query ^5  → 数据获取
framer-motion ^11 → 动画引擎（所有动画必须用它）
embla-carousel-react ^8   → 轮播（角色选择等）
sonner ^1.7       → toast 通知
howler ^2.2       → 音频播放（5层混合）
konva + react-konva ^9  → 场景热区（Canvas）
lucide-react ^0.460 → 图标（统一用这个，不引入其他图标库）
date-fns ^4.1     → 时间处理
```

---

## 二、核心设计哲学

### 2.1 三层沉浸法则（必须遵守）

```
Layer 1. 环境沉浸
  └─ 深色主题 + 场景背景图为主视觉 + 氛围音频
  └─ 玩家感知："我进入了一个世界"

Layer 2. 叙事沉浸
  └─ 角色对话 + 剧情推进 + 线索发现
  └─ 玩家感知："我在经历一个故事"

Layer 3. 心智沉浸
  └─ 推理思考 + 情绪代入 + 反转冲击
  └─ 玩家感知："原来是这样！"
```

### 2.2 "不是文字游戏"原则

```
❌ 不要做：
  - 全屏都是文字气泡
  - 按钮平铺在页面
  - 缺乏视觉反馈的操作
  - 生硬的页面跳转

✅ 要做：
  - 场景图作为主视觉，UI半透明覆盖
  - 每次操作都有动画反馈
  - 音频氛围实时变化
  - 状态驱动UI风格动态转变
```

### 2.3 "不造轮子"清单

| 需求 | 使用方案 | 不自己实现 |
|------|---------|-----------|
| 动画 | framer-motion | CSS 手写动画（除非极简单场景） |
| 轮播/滑动 | embla-carousel | 手写滑动 |
| 通知提示 | sonner | 手写 toast |
| 图标 | lucide-react | 其他图标库或 SVG |
| 模态/抽屉 | shadcn/ui Dialog/Sheet | 手写弹窗 |
| 滚动条 | 原生 + CSS | 自定义滚动条库 |
| 表单 | 原生 HTML + React state | 表单库 |
| 音频 | Howler.js | 原生 Web Audio API |
| 场景交互 | Konva.js | 手写 Canvas |
| 状态管理 | Zustand | Redux/MobX |

---

## 三、视觉设计规范

### 3.1 色板系统

```
/* CSS 变量在 globals.css 中定义，组件通过 var() 引用 */

--background: #0a0a0b;           // 主背景（纯黑偏暖）
--foreground: #e4e4e7;           // 正文字色（柔和白）
--muted: #27272a;                // 分割线/边框
--muted-foreground: #a1a1aa;     // 辅助文字灰
--border: #27272a;               // 边框
--accent: #18181b;               // 卡片/面板背景

--theme-primary: #7c3aed;        // 主色调（神秘紫）
--theme-secondary: #1e293b;      // 次要色
--theme-accent: #f43f5e;         // 强调色（危险/反转）

--danger: #dc2626;               // 错误/危险
--warning: #f59e0b;              // 警告/遗漏
--success: #22c55e;              // 成功/正确

--overlay: rgba(0,0,0,0.7);      // 遮罩
--panel-bg: rgba(10,10,11,0.95); // 面板背景（半透明）
--scene-overlay: rgba(0,0,0,0.3); // 场景暗角

渐变应用:
  ┌─ 按钮/高亮: bg-[var(--theme-primary)]
  ├─ 危险时刻: border/文字变 [var(--theme-accent)]  
  ├─ 发现线索: 闪光 [var(--info)]
  └─ 场景暗角: 叠加 [var(--scene-overlay)]
```

### 3.2 排版

```css
/* 正文字体：系统无衬线（提高阅读性） */
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }

/* 角色对话：无衬线 */
.chat-npc { font-family: inherit; }

/* DM旁白：斜体+居中 */
.dm-narration { font-style: italic; text-align: center; }

/* 线索/证据描述：等宽（可选） */
.clue-text { font-family: "JetBrains Mono", monospace; }
```

### 3.3 圆角规范

```
按钮/输入框: rounded-lg (8px)
卡片/面板: rounded-xl (12px)
模态框: rounded-2xl (16px)
头像: rounded-full
```

---

## 四、页面实现指引

### 4.1 `/library` — 剧本库

```
目的：选剧本入口，要有"进入某个世界"的仪式感

布局：
  顶部: 固定导航栏（半透明 + backdrop-blur）
  主视觉: 当前焦点剧本的大海报（占60vh），带渐变遮罩到底部
  下方: 网格展示已发布剧本卡片

响应式：
  桌面: 3列卡片网格
  平板: 2列
  手机: 1列 + 主视觉缩短到40vh

交互要点：
  ├─ 鼠标悬停卡片: 轻微上浮 + 边框发光 (framer-motion whileHover)
  ├─ 触控: 点击卡片 → 路由跳转 /library/[id]
  ├─ 筛选: 顶部有难度/类型标签按钮组
  └─ 加载: 卡片背面模糊占位，图片懒加载

必须的 framer-motion 动画：
  ├─ 页面入场: 整体 fadeIn (0.5s)
  ├─ 卡片入场: staggerChildren, 每个卡片从下往上+轻微透明
  └─ 悬停: scale: 1.02, borderColor 变主题色
```

### 4.2 `/library/[id]` — 剧本详情

```
布局：
  顶部: [返回] 按钮浮在左上
  视频/海报区: 宣传视频（静音自动播放，点击出声）
  信息区: 标题/难度/时长/标签
  故事简介: 段落文字
  角色预览: 圆形头像网格
  CTA: [开始游戏] 按钮浮动在底部

角色预览交互：
  点击头像 → 弹出角色简介卡片（Dialog）
  角色简介包含：名言/性格/背景/knows/doesnt_know

手机适配：
  └─ 视频区缩短
  └─ CTA 按钮固定底部（sticky bottom-0）
  └─ 角色头像 3列→2列
```

### 4.3 `/play/[sessionId]/select` — 角色选择

```
这是玩家"成为角色"的第一步，仪式感要强。

布局：
  桌面: 居中大卡片，角色海报全高展示
        下方缩略图列表（左右箭头或缩略图点击切换）
  手机: 全屏滑动 (embla-carousel)
        覆盖整屏的角色海报
        底部叠层：角色名 + 名言 + [选择]按钮

交互：
  ├─ 切换角色时有平滑过渡（当前角色淡出 → 新角色淡入）
  ├─ 选中的角色卡片有发光边框 (pulse-glow)
  ├─ 点击[确定选择] → 调用 POST /sessions → 跳转游戏页
  └─ 选择后有简约"锁定"动画

framemotion:
  ├─ AnimatePresence 包裹切换
  ├─ 角色卡片: 切换时 opacity + x 偏移
  └─ 选中: scale 1.02 + boxShadow glow

手机:
  ├─ embla-carousel 全屏滑
  ├─ 触摸友好: 滑动切换 + 点击下方按钮选择
  └─ 底部安全区适配
```

### 4.4 `/play/[sessionId]` — 游戏主界面（核心页面）

这是**最重要的页面**，投入50%的精力在这里。

#### 4.4.1 5层 Layout 结构

```
z-index 结构（从低到高）:

Layer 0: 纯黑背景 (z-0)
  └─ 场景切换过渡时显示

Layer 1: 场景背景 (z-10)
  └─ 全屏铺满, object-cover
  └─ 叠加 scene-overlay (暗角渐变)

Layer 2: Konva 热区层 (z-20) ← 只有桌面端
  └─ 可选：手机端用绝对定位的 HTML 按钮替代
  └─ 热区: 发光描边 + hover放大

Layer 3: 顶部操作栏 (z-30)
  └─ 毛玻璃效果: bg-[var(--background)]/60 backdrop-blur-md
  └─ 左侧: 场景名
  └─ 右侧: [线索板] [背包] [笔记] [设置] 图标按钮

Layer 4: 底部对话/叙事区 (z-40)
  └─ 毛玻璃效果: bg-[var(--background)]/80 backdrop-blur-md
  └─ 对话列表 + 输入框
  └─ 高度: 桌面40vh, 手机50vh（可拖拽调整高度）

Layer 5: 模态面板 (z-50) 
  └─ 线索板/背包/笔记: sheet 从右侧滑出（桌面）或底部弹出（手机）
```

#### 4.4.2 对话区设计

```
对话是核心交互，但不是"全屏都是文字"。

布局（底部上滑面板）:
  ┌──────────────────────────────────────┐
  │  王大达 · 饭店老板      情绪: 😰     │  ← 角色头+情绪图标
  │                                      │
  │  "你们可算来了！我等了半天了。"       │  ← NPC气泡（灰底左对齐）
  │                       12:30         │
  │                                      │
  │  "你昨晚听到了什么？"                 │  ← 玩家气泡（主题色底右对齐）
  │                       12:31         │
  │                                      │
  │  ～ 王大达显得有些不自然 ～            │  ← 动作描述（斜体居中）
  │                                      │
  │  ┌────────────────────────┐          │
  │  │ 输入问题...     [发送] │          │  ← 输入区
  │  └────────────────────────┘          │
  │  @王大达  @DM   [出示证物]  [使用卡牌]  │  ← 快捷操作
  └──────────────────────────────────────┘

情绪表达（关键！让NPC"有表情"）:
  ├─ NPC 头像旁有情绪图标（😊正常/😰紧张/😡愤怒/😱恐惧/😏撒谎）
  ├─ NPC 文字背景色随情绪微妙变化
  ├─ 撒谎时文字加红色左边框 (border-l-2 border-[var(--danger)])
  ├─ 恐惧时文字颜色变淡 + 颤抖动画
  └─ NPC "打字中" 头像脉动动画

输入区:
  ├─ placeholder: "输入你的问题… @角色名"
  ├─ 按回车发送
  ├─ 快捷按钮: @角色 / @DM / [出示证物] / [卡牌]
  └─ 手机: 输入框获得焦点时，对话区自动滚动到底

LLM 等待反馈:
  ├─ 0-3s: NPC 头像+ 打字闪烁 "..."
  ├─ 3-10s: 显示 "王大达正在思索……" + 思考表情
  └─ >10s: "还在回忆中，要不先看看其他线索？" + [查看线索板]
```

#### 4.4.3 场景交互（"不是文字游戏"的体现）

```
场景区是视觉锚点，支持两种模式：

模式A: Konva 热区（桌面端主力）
  ├─ 导入场景背景图作为 Canvas 底图
  ├─ 可交互区域用发光描边 + hover放大
  ├─ 点击热区 → action.perform("examine_scene", {hotspot})
  └─ 热区有悬浮标签：🔍 奇怪脚印 / 🚪 后门

模式B: HTML 热区（手机端+降级方案）
  ├─ 场景背景用 <img> 或 <div> CSS background
  ├─ 热点用绝对定位 <button> 叠加
  ├─ touch 友好：最小 44x44px
  └─ 点击涟漪动画

场景切换动画:
  ├─ framer-motion AnimatePresence
  ├─ 旧场景: opacity 1→0, scale 1→ 1.05 (0.5s)
  ├─ 黑屏停顿: 0.3s
  └─ 新场景: opacity 0→1, scale 0.95 → 1 (0.8s)
```

#### 4.4.4 状态驱动 UI（"眼前一亮"的关键）

UI 必须随游戏状态变化，让玩家感受到"世界在回应我"：

```
游戏状态 → UI 变化
─────────────────────────────────────────────────
正常调查阶段:
  场景正常亮度 (scene-overlay: 0.3)
  BGM 轻柔
  对话区正常白底气泡
  NPC 表情: 正常/好奇

关键线索发现:
  屏幕中心闪光 (0.3s白色淡入淡出)
  线索卡从中心放大弹出
  音效: sfx_discovery
  对话区高亮显示线索文本

紧张/对峙:
  暗角加深 (scene-overlay: 0.3 → 0.6)
  BGM 切换为紧张版 (crossfade 2s)
  对话区边缘微红
  NPC 文字抖动

剧情音频播放:
  弹出字幕面板（半透明黑底，白色大字）
  场景锁定（不可操作，可暂停）
  顶部显示进度条
  播放完后自动恢复操作

反转/恐怖:
  屏幕闪烁 (flash 动画)
  色调偏移 (filter: hue-rotate)
  BGM 突变
  字幕文字变红

真相揭示:
  全屏切换（Layer 0-4 全部隐藏）
  只有文字 + 音频 + 背景渐变
  "真相时刻" 大字淡入
```

#### 4.4.5 响应式设计规则

```css
/* 断点 */
--sm: 640px    /* 手机 */
--md: 768px    /* 平板 */
--lg: 1024px   /* 桌面 */
--xl: 1280px   /* 大屏 */

/* 布局差异 */
桌面 (lg+):
  场景: 占 65vh
  对话: 右下角浮动，max-w-lg
  热区: Konva Canvas
  面板: 右侧滑出 Sheet

平板 (md):
  场景: 占 55vh
  对话: 全宽底部
  热区: HTML 按钮
  面板: 右侧 Sheet

手机 (sm):
  场景: 占 45vh
  对话: 全宽底部，占 40vh
  热区: HTML 按钮，44px 最小尺寸
  面板: 底部弹出式 Drawer
  操作栏: 图标缩小，文字隐藏
  输入框: 固定底部（键盘弹出时自动上移）

触摸优化:
  ├─ 所有按钮最小 44x44px（WCAG 标准）
  ├─ 滑动可关闭面板（拖拽式 Sheet/Drawer）
  ├─ 长按/3D Touch 用于证据组合
  └─ 触觉反馈: navigator.vibrate(20) 在关键操作时
```

### 4.5 线索板（模态面板）

```
激活: 点击顶部 [线索板]

布局：
  桌面: Sheet 从右侧滑出 (w-[480px])
  手机: Drawer 从底部弹出 (h-[85vh])

内容:
  ┌─ Tab: [第一轮] [第二轮] [第二本] [全部]
  ├─ 线索卡片瀑布流
  │   ├─ 缩略图 + 标题 + ★关键标记
  │   ├─ 点击 → 大图查看模式
  │   └─ 未发现的线索: 模糊占位 "???"
  └─ 底部: 进度 4/7 已发现

交互:
  ├─ 点击线索 → Dialog 弹出大图+详细文本+状态
  ├─ 长按 → 进入"关联模式" → 拖拽到另一条线索建立关联
  ├─ 标记为重要 → 星标钉在顶部
  └─ 手机: 左右滑动切换线索卡片

动画:
  ├─ 面板打开: slideInRight (桌面) / slideInUp (手机)
  ├─ 线索卡片: staggerChildren 逐个淡入
  └─ 大图模式: scale 弹出
```

### 4.6 证物背包

```
激活: 点击顶部 [背包]

布局:
  桌面: Sheet 右侧 (w-[480px])
  手机: Drawer 底部

内容:
  ┌─ 选中证物大图（居中）
  ├─ 证物名 + 描述（表层/深层）
  ├─ 状态: 已调查 | 已出示给 王大达
  └─ 操作: [出示] [组合] [用于推理]
  └─ 底部: 缩略图列表（水平滚动）

交互:
  ├─ 点击 [出示] → 弹角色列表 → 选择 → action.perform("show_evidence", {...})
  ├─ 点击 [组合] → 进入组合模式 → 选另一个证物 → 组合推理
  └─ 点击 [用于推理] → 加入最终提交证据链
```

### 4.7 最终推理

```
触发条件: 玩家在指定阶段提交或主动进入

布局: 全屏 modal
  ┌─ 指控对象: [下拉选择角色]  ← 只列出已接触的角色
  ├─ 作案动机: [下拉选择动机]
  ├─ 关键证据: [多选复选框]    ← 只列出已发现的证物
  └─ 推理描述: [文本区]

提交后:
  ├─ 信封飞入动画 (framer-motion)
  ├─ "正在提交你的推理…" (3-5s loading)
  └─ 结果: 触发对应结局

注意: 如果是假结局(stage.meta.is_fake)，看起来一样但触发的剧情不同
```

### 4.8 真相揭示

```
触发: 最终推理提交后

布局: 全屏覆盖，所有UI隐藏
  ┌─ 纯黑背景
  ├─ 文字逐字出现 (打字机效果)
  ├─ 背景音频: 真相 BGM
  ├─ 关键节点: 角色独白浮出
  └─ 结局分支: 根据提交内容播放不同结局视频/音频

动画:
  ├─ 文字: framer-motion 逐字入场 (letter animation)
  ├─ 独白: fadeInUp
  └─ 结局: 全屏过渡
```

### 4.9 复盘评分

```
布局: 全屏滚动页面
  ┌─ 评分大数字 (动画计数效果)
  ├─ 评级: S/A/B/C/D
  ├─ 正确项 (绿色 ✓)
  ├─ 遗漏项 (黄色 ⚠)
  ├─ 推理路径对比
  │   你的: A → B → C
  │   最优: A → D → E → C
  ├─ 真相摘要 (完整故事)
  └─ [再来一次] [分享结果] [问卷调查]

动画:
  └─ 数字: framer-motion useSpring 动画计数
```

### 4.10 阶段切换横幅

```
触发: stage.changed WebSocket 事件

UI: 顶部滑入横幅 (停留3秒后滑出)

  ┌──────────────────────────────────┐
  │  ● 第一幕 · 第一轮搜证           │
  │  雪地的脚印指向了饭店后门……       │
  └──────────────────────────────────┘

动画:
  滑入: translateY(-100%) → 0 (0.5s, easeOut)
  停留: 3s
  滑出: 0 → translateY(-100%) (0.5s, easeIn)

framemotion: AnimatePresence + motion.div
```

---

## 五、音频系统实现

### 5.1 音频层级

```typescript
// Howler.js 5 层独立控制
// 所有音频通过 WebSocket media.* 事件驱动

层级 0: Ambient (环境音)   → 始终循环，低音量 0.2
层级 1: BGM (场景音乐)    → 按场景切换，中音量 0.35
层级 2: Story (剧情音频)  → 单次播放，高音量 0.7
层级 3: Voice (语音/TTS)  → 单次播放，中音量 0.5
层级 4: SFX (音效)        → 瞬间播放，中低音量 0.4

每个层级:
  ├─ 独立的 Howl 实例池
  ├─ 独立的音量控制
  └─ 独立的状态（playing/paused/stopped）
```

### 5.2 音频事件处理

```typescript
// 从 WebSocket media.play 事件 → AudioManager
ws.on("media.play", (data) => {
  switch (data.type) {
    case "bgm":
      audioManager.crossfadeBGM(data.asset_id, data.options?.fade_in || 2);
      break;
    case "story":
      audioManager.playStory(data.asset_id, data);
      showSubtitle(data.subtitle_url);
      break;
    case "sfx":
      audioManager.playSFX(data.asset_id);
      break;
  }
});
```

### 5.3 音频控制UI

```
底部常驻: 音频图标 + 当前曲目名

点击展开控制面板:
  ┌──────────────────────────┐
  │ 总音量: ████████░░       │
  │ 音乐:   ██████░░░░       │
  │ 语音:   ███████░░░       │
  │ 音效:   █████░░░░░       │
  │                          │
  │ 正在播放: 雪乡夜色 02:34  │
  │ [自动播放] [字幕] [跳过]   │
  └──────────────────────────┘
```

---

## 六、动画清单（framer-motion）

### 6.1 页面过渡

```typescript
// 所有页面之间
const pageTransition = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
  transition: { duration: 0.3, ease: "easeInOut" }
};

// 用在每个 page 组件外层:
<motion.div {...pageTransition}>
  <YourPage />
</motion.div>
```

### 6.2 列表入场

```typescript
// 卡片/线索列表
const container = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.08 }
  }
};
const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
};

<motion.div variants={container} initial="hidden" animate="show">
  {items.map(item => (
    <motion.div key={item.id} variants={item}>
      <Card />
    </motion.div>
  ))}
</motion.div>
```

### 6.3 情绪动画

```typescript
// NPC 恐惧颤抖
<motion.div
  animate={emotion === "fear" ? { x: [0, -2, 2, -2, 0] } : {}}
  transition={{ duration: 0.3, repeat: Infinity }}
>
  {text}
</motion.div>

// 屏幕闪光
<motion.div
  initial={{ opacity: 0 }}
  animate={{ opacity: [0, 0.8, 0] }}
  transition={{ duration: 0.3 }}
/>
```

### 6.4 场景切换

```typescript
<AnimatePresence mode="wait">
  <motion.div
    key={sceneId}
    initial={{ opacity: 0, scale: 1.05 }}
    animate={{ opacity: 1, scale: 1 }}
    exit={{ opacity: 0, scale: 0.95 }}
    transition={{ duration: 0.6 }}
  >
    <SceneBackground />
  </motion.div>
</AnimatePresence>
```

### 6.5 其他必须动画

```
├─ 线索解锁: 卡片从中心弹出 (scale 0→1 + opacity)
├─ 证物出示: 证物飞到角色头像 (position animation)
├─ 阶段切换: 横幅下滑入 (translateY)
├─ 提交推理: 信封飞入 (path animation)
├─ 真相揭示: 文字打字机 (letter-by-letter)
├─ 评分数字: spring 动画计数
├─ 面板开关: slideInRight (桌面) / slideInUp (手机)
├─ toast 提示: slideIn + fadeOut
├─ 提示推送: 右下角淡入 (5s后消失)
└─ 热区悬停: scale + glow (whileHover)
```

---

## 七、移动端专项

### 7.1 布局适配

```
每个页面必须测试 375px (iPhone SE) 到 428px (iPhone Pro Max)

关键手机适配:
├─ 游戏主界面:
│   ├─ 场景区: 45vh (比桌面少，给对话区留空间)
│   ├─ 对话区: 40vh + 键盘弹出时自动上移
│   ├─ 热区: 改用绝对定位 <button> (44px min)
│   ├─ 操作栏: 图标 + 无文字标签
│   └─ 面板: 底部弹出 (Drawer 风格)
│
├─ 剧本库:
│   ├─ 主视觉: 40vh
│   ├─ 卡片: 1列
│   └─ 筛选: 水平滚动 chips
│
├─ 角色选择:
│   └─ embla-carousel 全屏滑动
│
└─ 线索板/背包:
    └─ 底部 Drawer (85vh) + 拖拽关闭
```

### 7.2 触摸交互

```typescript
// 滑动关闭面板 (framer-motion drag)
<motion.div
  drag="y"
  dragConstraints={{ top: 0, bottom: 100 }}
  onDragEnd={(_, info) => {
    if (info.offset.y > 100) closePanel();
  }}
>
  <PanelContent />
</motion.div>

// 触觉反馈
const hapticFeedback = (pattern: number[] = [20]) => {
  if (navigator.vibrate) navigator.vibrate(pattern);
};
// 关键操作时调用: 提交推理 / 发现线索 / 反转时刻
```

### 7.3 安全区域

```css
/* 适配刘海屏/圆角屏 */
.safe-top {
  padding-top: env(safe-area-inset-top);
}
.safe-bottom {
  padding-bottom: env(safe-area-inset-bottom);
}

/* 游戏主界面主体区域 */
.game-main {
  height: calc(100vh - env(safe-area-inset-top) - env(safe-area-inset-bottom));
}
```

### 7.4 全屏模式

```typescript
// 进入游戏时请求全屏
const enterFullscreen = () => {
  const el = document.documentElement;
  if (el.requestFullscreen) el.requestFullscreen();
};

// 在 play/[sessionId] 页面，用户首次交互时调用
// 注意: 全屏 API 需要用户手势触发
```

---

## 八、必须使用的开源库清单

| 库 | 用途 | 必须使用场景 |
|----|------|-------------|
| framer-motion | 所有动画 | 页面过渡、列表入场、模态开关、情绪动画、场景切换 |
| embla-carousel-react | 轮播 | 角色选择页、线索滑动浏览 |
| sonner | toast | 提示推送、系统通知、错误提示 |
| howler | 音频 | 所有 BGM/剧情音频/语音/音效 |
| lucide-react | 图标 | 所有 UI 图标，不引入其他图标库 |
| konva + react-konva | 场景热区 | 桌面端可交互场景（手机端用 HTML 替代） |
| zustand | 状态管理 | 全局游戏状态（已实现，直接用） |
| @tanstack/react-query | 数据获取 | API 调用封装 |
| date-fns | 时间 | 聊天时间戳格式化 |

### 不引入的库
```
❌ Redux / MobX (用 Zustand)
❌ Bootstrap / Ant Design (用 Tailwind + shadcn/ui 风格)
❌ Chart.js / Recharts (复盘分数用大字+图标展示即可，不需要图表)
❌ jQuery (不需要)
❌ i18n (暂时不需要多语言)
❌ GSAP (framer-motion 覆盖所有需求)
```

---

## 九、分阶段实现计划

### Phase 1: 核心框架 + 游戏主界面 (投入50%精力)
```yaml
1. 完善 globals.css 主题系统
2. 用 framer-motion 包装所有 page 过渡
3. 实现游戏主界面 5层布局
4. 实现对话系统（含情绪表达 + LLM等待反馈）
5. 实现音频管理器 (Howler.js 5层)
6. 实现状态驱动 UI（亮度/色调随游戏变化）
7. 实现场景切换动画

验收: 能在浏览器里打开游戏页，看到场景，发消息，
      有 BGM，切换场景有动画
```

### Phase 2: 交互面板 (30%精力)
```yaml
1. 线索板（右侧Sheet/底部Drawer）
2. 证物背包
3. 卡牌系统
4. 场景热区交互（桌面Konva/手机HTML）
5. 快捷操作栏（@角色 / [出示证物]）
6. 阶段切换横幅

验收: 所有面板可打开关闭，证物可出示，
      线索可查看，阶段切换有动画
```

### Phase 3: 完整流程 + 打磨 (20%精力)
```yaml
1. 剧本库 + 详情页（API对接）
2. 角色选择页（embla-carousel）
3. 最终推理 + 真相揭示
4. 复盘评分（数字动画）
5. 移动端适配专项
6. 边缘情况处理（loading/error/empty state）

验收: 全流程跑通，移动端可用，动画流畅
```

---

## 十、代码质量要求

```typescript
// 1. 组件拆分粒度
// 一个文件不超过 200 行
// 如果一个组件太长，拆成子组件

// 2. 组件结构
// components/game/    ← 游戏专属组件
// components/ui/      ← 通用UI组件（或 shadcn/ui）
// components/layout/  ← 布局组件

// 3. 注释要求
// 复杂逻辑块必须注释"为什么"
// framer-motion 动画关键帧加注释说明效果
// WebSocket 事件处理加注释说明来自 API_REFERENCE.md 哪一节

// 4. 不要做
// - 不要引入本文档未列出的库
// - 不要修改 store/gameStore.ts 的结构（可以扩展字段）
// - 不要删除骨架中已有的文件
// - 不要直接调用 API 路径，用 lib/api.ts 的封装
```

---

## 十一、实现后验证清单

```
□ 前端 npm run build 通过，无 TS 错误
□ 所有 7 条路由可访问
□ 从剧本库→选本→选角→游戏→推理→复盘 全流程跑通
□ mock 模式下（无后端）页面不应白屏，显示友好提示
□ 桌面端 (1440px) 所有功能正常
□ 手机端 (375px) 所有功能正常
□ 面板打开关闭动画流畅 (60fps)
□ BGM/剧情音频可以播放和切换
□ 场景切换动画正常
□ 对话可发送和接收（WebSocket mock）
□ 线索板和背包可打开
□ 阶段切换横幅有动画
□ 状态驱动UI（紧张时变暗等）有效果
□ 404/loading/error 状态有展示
□ 没有引入多余的 npm 包
```
