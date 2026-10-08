# 智能课本助手 — 项目参考

> 用于 `--help` / CLI 帮助信息开发的参考文档  
> 最后更新: 2026-05-25

## 目录结构

```
vibecoding/
├── apps/
│   ├── web/                              # Next.js 16 前端 (port 3000)
│   │   ├── src/
│   │   │   ├── app/
│   │   │   │   ├── layout.tsx            # 根布局（导航栏 + 全局样式）
│   │   │   │   ├── page.tsx              # 首页（上传入口 + 课本列表）
│   │   │   │   └── textbook/
│   │   │   │       └── [id]/
│   │   │   │           ├── page.tsx      # 课本详情（章节目录）
│   │   │   │           └── chapter/
│   │   │   │               └── [chapterId]/
│   │   │   │                   └── page.tsx  # 章节阅读 + 难度选择 + AI 问答
│   │   │   └── lib/
│   │   │       └── api.ts                # 后端 API 调用封装
│   │   ├── next.config.ts
│   │   ├── tsconfig.json
│   │   └── package.json
│   │
│   └── api/                              # FastAPI 后端 (port 8081)
│       ├── main.py                       # 应用入口 + CORS + 路由注册
│       ├── config.py                     # pydantic-settings 配置管理
│       ├── db.py                         # SQLAlchemy 引擎 + Session
│       ├── requirements.txt
│       ├── routers/
│       │   ├── upload.py                 # POST /api/upload
│       │   ├── textbooks.py              # GET /api/textbooks, /api/textbooks/:id
│       │   ├── chapters.py               # GET /api/textbooks/:id/chapters/:cid
│       │   └── generation.py             # POST /api/textbooks/:id/chapters/:cid/generate
│       ├── services/
│       │   ├── parser.py                 # PDF 解析：PyMuPDF TOC 提取 + 字号启发式分章
│       │   └── generator.py              # LLM 讲解生成：OpenAI 兼容接口 + 模板降级
│       └── models/
│           ├── textbook.py               # Textbook ORM 模型
│           └── chapter.py                # Chapter ORM 模型
│
├── docs/
│   └── project-reference.md              # 本文件
├── .gitignore
├── .env.example
├── pnpm-workspace.yaml
├── package.json                          # 根 package.json（monorepo 脚本入口）
├── Makefile
├── docker-compose.yml
└── CLAUDE.md
```

## 技术栈

| 层 | 技术 | 版本 |
|----|------|------|
| 前端框架 | Next.js (App Router + Turbopack) | ^16 |
| UI 样式 | Tailwind CSS | ^4 |
| 语言 | TypeScript | ^5 |
| 后端框架 | FastAPI | ^0.136 |
| ORM | SQLAlchemy | ^2 |
| PDF 解析 | PyMuPDF (fitz) | ^1.27 |
| LLM SDK | openai | ^2.38 |
| 数据库 | SQLite (开发) → PostgreSQL (生产) | — |
| 包管理 | pnpm (monorepo) + pip (venv) | pnpm ^9 |
| Python | CPython (venv) | ^3.11 |

## API 路由表

| Method | Path | Request Body | 说明 |
|--------|------|-------------|------|
| `GET` | `/api/health` | — | 健康检查 |
| `POST` | `/api/upload` | multipart: `file` | 上传课本 PDF（自动分章解析） |
| `GET` | `/api/textbooks` | — | 课本列表 |
| `GET` | `/api/textbooks/{id}` | — | 课本详情（含章节目录） |
| `GET` | `/api/textbooks/{id}/chapters/{cid}` | — | 章节详情（含原文或讲解） |
| `POST` | `/api/textbooks/{id}/chapters/{cid}/generate` | `{"difficulty":"medium","style":"teacher"}` | 生成 AI 讲解 |

### generate 请求参数

| 参数 | 类型 | 可选值 | 默认值 | 说明 |
|------|------|--------|--------|------|
| `difficulty` | string | `easy` / `medium` / `hard` | `medium` | 讲解难度 |
| `style` | string | `teacher` / `concise` / `story` | `teacher` | 讲解风格 |

## 前端路由表

| 路径 | 类型 | 说明 |
|------|------|------|
| `/` | 静态 | 首页（上传入口 + 课本列表） |
| `/textbook/[id]` | 动态 | 课本详情（章节目录 + 生成状态） |
| `/textbook/[id]/chapter/[chapterId]` | 动态 | 章节阅读 + 难度选择 + AI 问答 |

## 日常命令

```bash
# ===== 环境准备 =====
make install                # 安装所有依赖（前端 + 后端 venv）

# ===== 开发 =====
pnpm dev                    # 启动前端 dev server (localhost:3000)
pnpm dev:api                # 启动后端 dev server (localhost:8081)

# ===== 构建 & 检查 =====
pnpm build                  # 前端生产构建
pnpm lint                   # ESLint 检查

# ===== 清理 =====
make clean                  # 删除 node_modules, .venv, .next, __pycache__
```

## 环境变量

参见 `.env.example`：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite:///./data/app.db` | 数据库连接串 |
| `LLM_API_KEY` | — | LLM API 密钥（不配置则使用模板降级） |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | LLM API 地址（支持 OpenAI / DeepSeek / 通义千问 等兼容接口） |
| `LLM_MODEL` | `gpt-4o` | 默认模型 |
| `LLM_TEMPERATURE` | `0.7` | 生成温度（0-2） |
| `LLM_MAX_TOKENS` | `4096` | 最大输出 token 数 |
| `MAX_UPLOAD_SIZE_MB` | `50` | 上传文件大小上限 |
| `CORS_ORIGINS` | `http://localhost:3000` | 允许的跨域来源 |

## 核心数据流

```
用户上传 PDF
  → parser.py: PyMuPDF 提取 TOC → 按章节分页 → 提取文本 → 存入 Chapter 表
  → 前端 textbook/[id] 页展示章节目录
  → 用户进入章节 → 选择难度 → POST /generate
  → generator.py: 读取章节原文 → 拼装 prompt → 调用 LLM API
     ├─ 有 API key → OpenAI 兼容 API → 返回 AI 讲解
     └─ 无 API key → 返回结构化模板（含本节导入/概念讲解/例题/误区/速记）
  → 前端渲染 Markdown 讲解内容
  → 用户可点击"重新生成"切换难度
```
