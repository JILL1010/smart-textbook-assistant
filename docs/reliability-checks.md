# 第一轮可靠性修复与验证

## 已实现

- 三种讲解风格进入实际模型提示词；接口拒绝未知难度或风格。
- 重新生成讲解时，数据库中的音频、题目和图谱被清空，旧音频及字幕文件被清理；页面同步重置并提示重新生成。
- 新增 `generation_revision` 字段。旧版本的配音、练习、图谱和讲解请求晚返回时，返回 HTTP 409，避免覆盖新内容。
- 配音使用一个 edge-tts 流，分段和时间偏移交给该库处理；依赖要求更新为 `edge-tts>=7.2.8,<8.0`。失败时清理部分文件。
- 刷新时读取保存的字幕，允许重新生成语音。切换章节重建该章状态，避免残留题目、分数和对话。
- 图谱绘制使用独立的数据副本，命中画布使用库提供的识别颜色，宽度由 ResizeObserver 更新。
- 上传按块读取并执行大小限制；超限返回 413，空文件/无效文档返回 400，解析失败清理文件并回滚。
- 浏览器统一请求同源 `/api`。Next.js 代理在运行时读取 `API_UPSTREAM_URL`，转发上传、错误和音频 Range；桌面启动器传入实际选定的端口。
- 桌面音频目录使用绝对路径。首页描述改为当前已实现的讲解、语音和练习功能。

## 开发与配置

在根目录运行前后端：

```powershell
pnpm dev
pnpm dev:api
```

前端默认代理到 `http://127.0.0.1:8081`。若后端使用其他地址，在前端启动前设置：

```powershell
$env:API_UPSTREAM_URL = 'http://127.0.0.1:8083'
pnpm dev
```

也可参照 `apps/web/.env.example` 设置前端 `.env.local`。旧的 `NEXT_PUBLIC_API_URL` 不再控制浏览器请求，地址不再固定进客户端构建。桌面启动器自动设置代理地址。

启动后端时会为旧数据库添加 `generation_revision`，默认值为 0。此迁移已用临时旧结构数据库验证，不会主动清空已有讲解或派生产物；只有成功重新生成该章讲解时才清理其旧派生产物。用户已有数据库和教材未用于本轮写入测试。

## 自动化检查

```powershell
apps/api/.venv/Scripts/python -m pip install -r apps/api/requirements-dev.txt
apps/api/.venv/Scripts/python -B -m unittest discover -s apps/api/tests -v
pnpm --filter web test
pnpm lint
pnpm --filter web exec tsc --noEmit --incremental false
pnpm build
```

测试使用临时数据库、文件和模拟 LLM/TTS，不消耗外部服务。代理测试使用 Node 内置测试框架。

## 浏览器验证

`apps/api/tests/smoke_server.py` 启动临时教材库和模拟生成服务。`apps/web/tests/browser-smoke.mjs` 使用 Playwright 与无头 Edge 验证真实页面。

先准备可用的 Playwright 模块，然后在两个终端分别启动：

```powershell
apps/api/.venv/Scripts/python -B apps/api/tests/smoke_server.py --port 18081
```

```powershell
$env:API_UPSTREAM_URL = 'http://127.0.0.1:18081'
pnpm --filter web dev --port 18080
```

再运行 `node apps/web/tests/browser-smoke.mjs`。默认检查 `http://127.0.0.1:18080`；可通过 `SMOKE_WEB_URL` 覆盖地址，通过 `PLAYWRIGHT_MODULE` 指定 Playwright 包目录。每次完整重跑前重启临时后端以恢复夹具，完成后停止两个测试服务。

浏览器脚本检查：图谱点击与关联概念、刷新恢复字幕、章节状态隔离、风格参数传递、重新生成后派生内容失效、上传限额错误，以及未捕获的页面异常。

## 本轮验证记录（2026-10-08）

- 后端业务、服务、迁移和桌面启动器回归：18 项通过。
- 代理回归：5 项通过。
- ESLint、TypeScript 和 Next.js 生产构建通过。
- 浏览器脚本在生产前端和实际 `.next/standalone/apps/web/server.js` 两条启动路径均通过，后端使用 18081 端口。
- 音频范围请求通过。字幕时间轴使用模拟配音流验证，尚未调用真实 TTS 做听音同步验收；模型使用模拟响应验证参数，尚未评价真实生成内容。
- 现有 `dist/` EXE 未重新打包；使用新功能需从修改后的源码运行，或重新构建桌面发行包。完整 PyInstaller 打包流程不属于本轮已验证项。
