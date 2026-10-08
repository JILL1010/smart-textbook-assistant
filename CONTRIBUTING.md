# 贡献指南

欢迎改进智能课本助手。较大的功能改动建议先开 Issue，说明使用场景和预期行为；修复明确的问题可直接提交 Pull Request。

## 开始开发

1. Fork 仓库并创建分支，例如 `fix/quiz-draft` 或 `feat/source-search`。
2. 按 [README](README.md) 安装依赖并配置本地 `.env`。
3. 阅读 [AGENTS.md](AGENTS.md) 中的目录与代码约定。接口变更同步更新 `apps/web/src/lib/api.ts`。

使用自己有权使用的教材进行本地测试。请勿提交 API 密钥、完整教材、数据库、音频或包含个人学习记录的日志。问题复现优先使用自建的最小文本或测试夹具。

## 验证改动

在仓库根目录运行受影响的检查：

```powershell
apps/api/.venv/Scripts/python -B -m unittest discover -s apps/api/tests -v
pnpm --filter web test
pnpm lint
pnpm --filter web exec tsc --noEmit --incremental false
pnpm build
```

后端测试依赖见 `apps/api/requirements-dev.txt`。测试使用临时数据库并模拟模型和语音服务；不要把测试请求发送到真实用户数据。页面改动请验证相关浏览器流程，参见 [可靠性检查](docs/reliability-checks.md)。

## 提交与 Pull Request

提交消息使用明确的动词，例如 `fix: preserve quiz draft on reload`。保持一次改动聚焦于一个问题。

PR 描述应包含问题、修改后的行为、关联 Issue 和实际执行的检查。页面变化附截图；若存在未验证项，请说明其范围。改变生成逻辑时，检查旧音频、练习、图谱和学习记录是否仍正确处理。

## 许可证

提交贡献表示你有权提供这些代码，并同意按仓库的 **AGPL-3.0-only** 许可证发布该贡献。无需签署额外贡献者协议。第三方代码必须保留其版权和许可证声明。
