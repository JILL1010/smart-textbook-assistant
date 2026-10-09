# 智能课本助手 · Smart Textbook Assistant

面向个人教材学习的本地应用：导入文字 PDF / DOCX，阅读 AI 讲解、提出带原文来源的问题、完成练习，并保存学习记录与错题。

## 功能

- PDF 目录 / 字号启发式分章、DOCX 标题分章。
- 按难度和风格生成讲解，长章节按原文顺序分段处理。
- 同一本教材的全文片段检索，优先当前章；回答区分教材依据与补充说明，可查看引用原文和文件位置。
- 语音讲解、字幕、覆盖完整讲解的选择题生成和交互式知识图谱；题目与概念显示来源片段。
- 持久化已读标记、作答草稿、成绩快照、错题和复习记录。
- 讲解、练习和图谱的后台任务：分段进度、刷新恢复、停止和从头重试。
- Next.js 同源 API 代理，以及 Windows 桌面启动器源码。

## 技术栈与目录

- `apps/web/`：Next.js 16、React 19、TypeScript、Tailwind CSS。
- `apps/api/`：FastAPI、SQLAlchemy、SQLite、PyMuPDF、python-docx、OpenAI 兼容接口、edge-tts。
- `apps/desktop/`：Python 启动器与 PyInstaller 构建脚本。
- `docs/`：设计、功能说明和验证记录。

## 本地运行（Windows / PowerShell）

准备 Node.js 20.9+、pnpm 9+ 和 Python（本项目测试环境为 Python 3.14）。在仓库根目录运行：

```powershell
pnpm install
python -m venv apps/api/.venv
apps/api/.venv/Scripts/python -m pip install -r apps/api/requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，填写自己的 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL`。若只体验原文检索和模板模式，将 `LLM_API_KEY` 留空。

分别在两个终端中运行：

```powershell
pnpm dev
```

```powershell
pnpm dev:api
```

访问 `http://localhost:3000`，API 文档位于 `http://localhost:8081/docs`。默认前端代理到 `http://127.0.0.1:8081`；其他端口通过 `API_UPSTREAM_URL` 配置，见 `apps/web/.env.example`。

数据库、教材和音频默认写入本地运行目录，不纳入版本控制。当前应用适合本地个人使用，尚未实现用户登录和多用户数据隔离。

## 检查与构建

```powershell
apps/api/.venv/Scripts/python -m pip install -r apps/api/requirements-dev.txt
apps/api/.venv/Scripts/python -B -m unittest discover -s apps/api/tests -v
pnpm --filter web test
pnpm lint
pnpm --filter web exec tsc --noEmit --incremental false
pnpm build
```

测试使用临时存储和模拟外部服务。GitHub Actions 在 push / PR 时运行后端测试、代理测试、lint、类型检查和生产构建。浏览器检查方法见 [可靠性验证](docs/reliability-checks.md)。生产前端构建为 Next.js standalone。

Windows 桌面打包（安装 `pyinstaller` 后）：

```powershell
apps/api/.venv/Scripts/python -m pip install pyinstaller
apps/api/.venv/Scripts/python apps/desktop/build.py
```

默认输出到新的 `dist/releases/<时间>/智能课本助手/`，不覆盖旧发行目录。包包含配置示例和许可证，不包含个人 `.env` 或教材。运行前在 EXE 旁复制 `.env.example` 为 `.env` 并填写配置。可用 `--skip-frontend --node-path 'C:/Program Files/nodejs/node.exe'` 复用已构建的前端与本机 Node。

## 当前边界

仅支持带文字的 PDF / DOCX，尚未加入 OCR。检索采用词项匹配；练习题量较少时，处理完整讲解后按顺序抽样，并显示实际片段覆盖比例。图谱按相同名称和类别合并节点，尚未做语义消歧。模型输出仍需核对，语音同步尚需真实听音验收。后台任务要求单进程运行，详见 [任务行为与恢复](docs/background-tasks.md)。

详见 [学习功能与验证记录](docs/learning-features.md)、[真实模型质量验收](docs/model-quality-evaluation.md)、[设计记录](docs/next-stage-design.md) 和 [贡献流程](CONTRIBUTING.md)。

## 开源与贡献

Copyright (C) 2026 JILL1010 and contributors.

本项目以 **GNU Affero General Public License v3.0（AGPL-3.0-only）** 发布，完整条款见 [LICENSE](LICENSE)。允许按许可证条款使用、修改和再分发，包括商业使用；再分发和修改版本的网络服务需遵守对应源码提供等要求。项目不提供任何担保。

PDF 解析依赖 PyMuPDF，其开源版本采用 AGPLv3；上游另提供商业授权，见 [PyMuPDF 授权说明](https://pymupdf.io/licensing)。第三方依赖保留各自的许可证；分发桌面包时也须保留其许可与版权声明。

欢迎通过 [Issues](https://github.com/JILL1010/smart-textbook-assistant/issues) 报告问题，或提交 Pull Request。贡献步骤和验证要求见 [CONTRIBUTING.md](CONTRIBUTING.md)，代码组织约定见 [AGENTS.md](AGENTS.md)。教材文件、个人学习数据和 API 密钥不包含在开源仓库中。
