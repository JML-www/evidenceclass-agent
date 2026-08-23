# 阶段九：原创 Web 产品验收

阶段九的前端工程位于 `apps/web`，采用 React + TypeScript + Vite。当前默认 Mock API，保证在基础设施未启动时仍能验收交互和状态；设置 `VITE_USE_MOCK_API=false` 后切换到阶段八 API。

## 验收命令

```powershell
Set-Location -LiteralPath "apps/web"
npm install
npm run build
npm run test:e2e
```

OpenAPI 类型边界可在仓库 Python 环境中离线重新生成：

```powershell
Set-Location -LiteralPath "."
.\.venv\Scripts\python.exe scripts\generate-web-openapi.py
```

该命令读取本地 FastAPI `app.openapi()`，生成 `apps/web/src/api/openapi.generated.ts`，不访问网络。

## 验收范围

- 任务中心：状态筛选、进度、加载/错误/空状态和状态一致的操作入口。
- 新建分析：单图、短视频和结构化模式，文件选择、隐私边界、上传进度和创建任务。
- Agent Run：节点时间线、工具摘要、耗时、重试次数、模型与费用摘要；不展示私有思维链。
- 证据浏览器：时间、标签、复核状态筛选；原始观察、确定性结果、LLM 解释三层明确区分。
- 复核工作台：媒体上下文、模型值、审核理由和确认/修正/拒绝入口。
- 结果与问答：`AnalysisResult` 展示、证据引用 chips、无依据回答边界和报告下载入口。
- 响应式布局：桌面、平板和窄屏下无横向溢出，控件有可访问名称。

当前运行结果：`npm audit --omit=optional`（使用官方 npm registry）、`npm test`、`npm run build` 和 `npm run test:e2e` 均通过。Playwright Chromium 使用本机缓存目录 `E:\playwright-browsers`；4 个 E2E 用例包含 1440、1024 和 390 宽度的响应式无横向溢出检查，并生成临时截图到被 Git 忽略的 `test-results/`。

## 跳过项与后续兼容性

以下项目仍明确跳过，但不会阻塞阶段十及后续阶段：

1. **真实 SSE 连续事件与断线重连的浏览器级验收**：客户端 `Last-Event-ID` 接缝和阶段八服务端单测已通过，但仍需带认证的真实 Worker 长连接场景；不能用 Mock 代替。
2. **真实 VLM/远端 OpenAI-compatible 模型效果**：需要有效模型授权和权重；当前远端接口此前返回 403，因此不伪造效果结论。
3. **Qwen 本地环境**：按用户明确要求，本轮不检查、不修改、不运行 Qwen。

已解决的离线部分：`scripts/generate-web-openapi.py` 已生成 15 个 TypeScript schema；新建分析页已接入 Job、签名 URL 上传、SHA-256 完成确认；复核按钮已接入 `decideReview` 适配器。真实后端调用只在有认证和基础设施时执行，不把 Mock 结果写成 live 证据。

这些跳过项都保持了稳定的类型和 API 边界，不会把 Mock 数据、未认证请求或未安装的浏览器运行时传递到后续阶段。
