# Windows 发行包验证（2026-10-09）

新包位于 `dist/releases/background-tasks/智能课本助手/`，包含持久化生成任务、学习记录和全文处理功能。旧 `dist/` 发行目录和原教材库保留不变。

## 构建

```powershell
pnpm build
apps/api/.venv/Scripts/python -m pip install pyinstaller
apps/api/.venv/Scripts/python -u -B apps/desktop/build.py --skip-frontend --node-path 'C:/Program Files/nodejs/node.exe' --output-dir dist/releases/background-tasks
```

本轮环境为 Python 3.14.2、PyInstaller 6.20.0 和 Node 24.13.0。默认不指定输出目录时，会新建时间戳目录。构建拒绝清理 `dist/` 外的路径，也拒绝覆盖包含 `.env` 或 `data/` 的发行目录。

Next.js standalone 资源由 Node 独立加载。pnpm 的目录链接被转换成实际文件，依赖从已追踪版本暴露为具名目录，不再重新联网安装。追踪到同名不同版本时明确失败，避免悄悄改变依赖解析。Python 使用 PyInstaller 的目录式打包；整包必须一起移动。

## 已完成验证

- 新 EXE 的隔离副本成功启动 FastAPI 与 Next.js。
- API 健康检查、首页、运行时同源代理和任务接口通过。
- 通过实际代理导入测试 PDF，启动讲解任务，保存并读取模板讲解；未调用外部模型。
- 测试服务已停止，测试副本已清理；发行目录未产生教材库或测试学习数据。
- 发行包扫描未发现已配置的 API 密钥、个人 `.env`、教材或学习数据库。
- 保留项目 AGPL 许可证、Node / Python 许可、Python 依赖许可，以及前端依赖中的许可文件。

本轮浏览器回归另外使用模拟教材和生产 standalone 前端，涵盖任务恢复、停止、重试及学习记录。桌面启动检查不代表真实 TTS 同步或模型教学质量合格；质量结果见 [模型验收](model-quality-evaluation.md)。
