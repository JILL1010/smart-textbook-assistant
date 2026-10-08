# 智能课本助手：源码阅读笔记

阅读日期：2026-10-08。依据为本地源码、已安装依赖、现有前端构建与只读数据库统计。

本文记录第一轮修复之前的源码状态。已实施的修复及当前验证结果见 [第一轮可靠性检查](reliability-checks.md)。

## 1. 项目定位

这是以课本章节为单位的 AI 学习工具。用户上传 PDF / DOCX，系统解析章节并保存原文，再生成讲解、语音、练习题和概念关系图，支持围绕章节原文的多轮问答。

目前的核心形态是本地 Web 应用，并有 Windows 桌面包装。桌面包装启动 FastAPI 和 Next.js，然后打开浏览器；没有独立原生学习界面。现有源码包含 MP3 与 JSON 字幕生成，没有视频渲染、合成或视频导出流程。首页与元数据中的“生成视频”描述超出了当前实现。

## 2. 阅读范围与检查边界

已阅读根目录开发说明、参考文档、包配置、Makefile、Compose、全部业务 Python 模块、前端页面、API 封装、主题与样式，以及桌面启动/打包和 launcher 测试脚本。没有找到仓库内 AGENTS.md；同时遵循用户在聊天中提供的指令。

没有修改业务源码、上传教材、数据库或现有构建。未调用真实 LLM 或 TTS，未启动桌面程序。数据库采用 SQLite `mode=ro` 连接，仅查询计数。本文不宣称完整运行或视觉验证通过。

## 3. 架构

```text
浏览器 / 桌面启动器打开的浏览器
    ↓
Next.js App Router（apps/web）
    ↓ fetch，统一封装在 src/lib/api.ts
FastAPI（apps/api，/api 前缀）
    ├─ 文档解析 → PyMuPDF / python-docx
    ├─ AI 生成与问答 → OpenAI 兼容 Chat Completions 接口
    ├─ 配音 → edge-tts
    └─ SQLAlchemy → SQLite + 上传文件 + MP3 / 字幕 JSON
```

前端 package.json 实际声明 Next.js 16.2.6、React 19.2.4、Tailwind 4 与 TypeScript 5；CLAUDE.md 中 Next.js 14 的描述已过时。UI 主要是手写 Tailwind 和 React 组件，未见实际使用 shadcn/ui 的组件体系。

关键入口：

| 文件 | 职责 |
|---|---|
| `apps/web/src/app/page.tsx` | 上传、课本列表、生成比例、删除 |
| `apps/web/src/app/textbook/[id]/page.tsx` | 课本信息和章节目录 |
| `apps/web/src/app/textbook/[id]/chapter/[chapterId]/page.tsx` | 讲解、原文、语音、练习、图谱和问答 |
| `apps/web/src/lib/api.ts` | 请求、返回类型和 API 地址 |
| `apps/api/main.py` | 生命周期、CORS、8 个路由模块 |
| `apps/api/services/parser.py` | 教材提取和分章 |
| `apps/api/services/generator.py` | LLM 提示词、讲解、练习和图谱校验 |
| `apps/api/services/tts.py` | 文本分段、配音流、字幕与文件保存 |
| `apps/desktop/launcher.py` | 路径、端口、服务启动和浏览器打开 |
| `apps/desktop/build.py` | standalone、便携 Node 和 PyInstaller 打包 |

## 4. 数据模型与状态

只有两个业务 ORM 实体：Textbook 和 Chapter。Textbook 保存标题、上传文件名与创建时间；Chapter 保存所属课本、顺序、标题、原文、单份生成讲解、音频文件名，以及序列化为文本的练习和图谱 JSON。

原文与讲解分字段保存，是合理的基础设计。现有模型没有生成版本、模型标识、难度/风格记录、生成时间、内容哈希或后台任务状态。再次生成会覆盖同一份讲解。

问答历史按课本/章节存入浏览器 localStorage；答题选择和分数在 React 内存状态中，刷新后不保存。题目和图谱本身会存入数据库。首页的进度条表示“章节讲解生成比例”，并不表示学习完成或知识掌握程度。

本次读取 `apps/api/data/app.db`：7 本课本、24 个章节，其中 4 个章节有非 NULL 讲解，3 个有音频文件名，2 个有练习数据，1 个有图谱数据；24 个章节原文均非空。这证明存在使用产物，不证明内容正确或功能全部可用。

## 5. 各条功能链

### 上传与解析

上传端点检查文件名和扩展名，生成 UUID 文件名、读取整个文件、写入磁盘并解析。PDF 优先采用内嵌目录，保留前两级条目；没有目录时依据页首标题格式和字号差异分章。DOCX 根据 Heading 1/2、中文标题样式，或短段落首 run 加粗识别标题。

限制：PDF 是页面级切分，同页出现多个目录条目时，前一个条目可能没有正文；没有 OCR，因此扫描版教材可能提取不到文字。DOCX 主要遍历普通段落，未实现表格、图片、公式和复杂版式的完整结构提取。模型也不保存原文页码与标题层级。

### 讲解

读取章节原文，最多使用前 8000 个字符，添加难度提示，发送固定教师讲解系统提示词。输出 Markdown，保存到 generated_content。未配置 Key 时返回模板讲解，模板仍会作为 generated_content 保存，计入“已生成”。

当前是直接把截断文本放入提示词，没有分块检索、向量索引、页码引用或 RAG。风格参数虽然贯穿 UI 和 API，但没有用于提示词。

### 问答

使用原文前 6000 个字符作为系统上下文，再附带最近 10 条 user/assistant 历史和本次问题。与讲解、出题的上下文来源不同。没有 Key 时返回配置说明；模型请求异常被转换为普通 answer，HTTP 层仍返回成功。

### 练习与知识图谱

两条接口均要求已有讲解，并优先使用生成讲解的前 8000 字符，而非原文。练习输出题目、4 个选项、答案下标与解析，浏览器判分。图谱输出概念节点和关系，校验/去重后保存，用 react-force-graph-2d 展示。

这意味着讲解里的错误或遗漏可能继续进入练习和图谱。现有图谱是单章节概念关系可视化，没有跨章节知识库、图查询或来源证据体系。

### 语音与字幕

优先朗读讲解，次选原文；清理 Markdown，以约 2000 字为目标按句子分段，使用中文 Xiaoxiao 语音，拼接 MP3 数据，保存字幕 JSON。前端具备播放、高亮、点击字幕跳转和音频下载入口。

### 桌面发行

构建流程是 Next standalone → 下载便携 Node → 重新安装生产 npm 依赖 → 拷贝后端资源 → PyInstaller。启动时后端在线程中运行，前端通过 Node 子进程运行；数据库和上传路径指向数据目录。

## 6. 已确认问题与后续修改入口

### A. 风格选择不生效

`services/generator.py:35` 的 generate_chapter_content 接收 style，但函数体不使用。离线用假客户端捕获调用参数：teacher、concise、story 三种风格的 messages 完全相同。修改入口是提示词构建，并同步保存所选参数。

### B. 讲解更新后，派生产物仍对应旧版本

`routers/generation.py` 只更新 generated_content；前端 handleGenerate 也仅更新该字段。audio_filename、quiz_data、knowledge_graph_data 未失效。用户重新生成后可能看到新讲解搭配旧语音、旧题目和旧图谱。音频存在时 UI 不显示重新生成语音按钮。

### C. 字幕时间累计有误，刷新后也不会恢复

`services/tts.py:55` 将已经包含 time_offset 的绝对结束时间再次累加到 time_offset。离线假 TTS 每段 1 秒，三段字幕起点实际得到 `[0, 1.3, 3.8999999]`；按现有 0.3 秒间隔假设应为 `[0, 1.3, 2.6]`。此外 MP3 拼接没有明确插入对应静音，时间轴不能只靠增加常量得到真实音频时长。

章节页仅在本次 generateTTS 响应后设置 subtitles，加载已有章节时没有请求已保存的字幕。刷新后音频仍在，字幕消失。

### D. 图谱点击与关联概念逻辑存在具体问题

章节页 `nodePointerAreaPaint` 忽略图谱库提供的识别颜色，使用 transparent 填充；本地 force-graph 源码表明这个回调用于绘制隐藏命中画布，会影响节点点击。

页面还将 graphData.edges 原对象直接传给图谱库，而本地 d3-force / force-graph 实现会把 link.source/target 从 ID 转成节点对象。随后详情面板仍使用 `e.source === selectedNode.id` 比较字符串，可能无法找出关联概念。以上基于应用和已安装库源码，尚未进行浏览器交互复现。

### E. 上传大小设置没有执行

config.py 定义 50MB 限额，但上传路由没有检查，直接 `await file.read()`。扩展名检查不能证明文件内容合法；解析失败时还缺少上传文件清理。上传解析采用同步文件写入、解析和数据库操作，位于 async 路由中，大文件会阻塞该处理路径。

### F. 无效练习答案会被改成 A

`generator.py:237` 对非法 answer 默认改成 0。离线传入 answer=99，结果变成 0。对教学内容，格式修复不能代替确定正确答案；此类题目应该判无效或重新生成。当前也没有严格保证返回题数等于请求题数，字段类型校验较宽松。

### G. 桌面动态端口与前端构建地址不一致

launcher.py 会自动选择空闲 API 端口，并在启动 Node 时设置 NEXT_PUBLIC_API_URL；现有 `.next/static/chunks` 中仍包含 `http://localhost:8081` 的客户端地址。当前打包方式没有提供浏览器动态获取 API 端口的配置链，默认端口被占用时可能连接旧服务或无法连接。这是构建与启动源码核对结论，尚未启动 EXE 进行端到端复现。

### H. 数据路径依赖启动工作目录

默认 `.env`、SQLite、uploads 和 data/audio 均使用相对路径。根目录 `pnpm dev:api` 与 desktop 开发入口使用的数据库/环境文件位置可能不同。桌面启动器明确设置数据库和上传绝对路径，但音频目录仍是相对 `data/audio`，不能保证所有数据都落在同一目录。

### I. 配置、依赖和文档存在漂移

- requirements.txt 声明 edge-tts `<7.0`，本地 venv 实际为 7.2.8，服务代码使用 SentenceBoundary。新环境是否支持相同事件需要重新验证。
- Compose 引用两个 Dockerfile，但源码目录中未找到对应文件；客户端地址 `http://api:8081` 也需要重新设计浏览器访问路径。
- Makefile install 假设 venv 已存在，未创建 venv；根 format 脚本调用前端未定义的 format。
- db.py 无条件传入 SQLite 的 check_same_thread 参数，不能仅换 DATABASE_URL 就认为 PostgreSQL 已支持。
- build.py 会把后端 `.env` 拷贝到发行目录，分发前应改用可编辑模板或用户配置，避免夹带个人凭证。

## 7. 检查结果

- TypeScript：`tsc --noEmit --incremental false` 通过。
- Python：21 个业务/桌面 Python 文件 AST 语法解析通过。
- 离线逻辑：风格消息相同、非法答案归零、字幕时间重复累计，均复现。
- 数据库：只读计数，未修改。
- ESLint：`eslint src` 未通过，4 个 error、0 个 warning。一个来自章节页第 133 行 effect 内同步 setChat；另外三个诊断来自第 791 行在渲染阶段读取 graphContainerRef.current。这些是当前 lint 规则报告，不等同于所有位置均已复现运行失败。
- 未验证：真实模型质量、真实 TTS 播放/时长、浏览器布局、EXE 完整启动、Docker 构建。

## 8. 综合理解

项目已具备学习工具的功能骨架：教材导入 → 章节讲解 → 练习反馈，以及问答、语音和图谱辅助。当前主要欠缺在教材结构保真、生成内容可信度、派生数据版本一致性与可复现运行配置。

继续迭代时，可先处理“设置真的生效、生成内容相互对应、图谱可点击、语音字幕可靠”这些已有功能，再考虑扩大教材类型和知识范围。若以后增加检索能力，应先解决长章节只读取开头的问题，并保留页码/段落来源；若要衡量教学效果，需要另外保存作答和学习记录，不能用生成比例代替学习进度。
