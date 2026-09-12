# 阶段九：原创 Web 产品验收

阶段九的前端工程位于 `apps/web`，采用 React + TypeScript + Vite。当前默认 Mock API，保证在基础设施未启动时仍能验收交互和状态；设置 `VITE_USE_MOCK_API=false` 后切换到阶段八 API。本轮补齐了「视觉与交互升级」与「结果页真实逻辑」两块验收缺口。

## 验收命令

```powershell
Set-Location -LiteralPath "apps/web"
npm install
npm run build      # tsc -b && vite build
npm test           # vitest run
npm run test:e2e   # playwright test
```

三条命令当前均通过（详见文末「当前运行结果」）。Playwright Chromium 使用本机缓存目录 `E:\playwright-browsers`；E2E 用例共 10 个（product 5 + responsive 1 + new-pages 4），覆盖 1440 / 1024 / 390 宽度响应式无横向溢出检查。为避免并行 worker 共享同一内存 Mock 导致状态竞争，`playwright.config.ts` 已设 `fullyParallel: false`。

OpenAPI 类型边界可在仓库 Python 环境中离线重新生成：

```powershell
Set-Location -LiteralPath "."
.\.venv\Scripts\python.exe scripts\generate-web-openapi.py
```

该命令读取本地 FastAPI `app.openapi()`，生成 `apps/web/src/api/openapi.generated.ts`，不访问网络。

## 验收范围（9 个页面）

- 任务中心：状态筛选、进度、加载/错误/空状态和状态一致的操作入口（取消/重试已接 Toast 反馈）。
- 新建分析：单图、短视频和结构化模式，文件选择、隐私边界、按模式的大小上限（VIDEO 2GB / IMAGE 20MB / STRUCTURED 10MB）与上传进度。
- Agent Run：节点时间线、工具摘要、耗时、重试次数、模型与费用摘要；不展示私有思维链（已移除伪造的 `Token 用量 12,480`，改为真实执行节点数）。
- 证据浏览器：时间、标签、复核状态筛选；原始观察、确定性结果、LLM 解释三层明确区分；已补 `isError` 错误态。
- 复核工作台：媒体上下文、模型值、审核理由和确认/修正/拒绝入口。
- 结果与问答：真实 `AnalysisResult` 展示、证据引用 chips、无依据回答边界和报告下载入口。
- 知识库：参考资料列表（已补 real-mode 错误态）。
- 评估集：数据集列表，无伪造指标。
- 设置：模型能力边界展示。
- 响应式布局：桌面、平板和窄屏下无横向溢出，控件有可访问名称。

## 视觉与交互升级

- **语义化设计令牌**：`src/styles/tokens.css` 三层表面（canvas/surface/raised）、二级边框、三级文本、品牌 + 语义色（success/warning/danger/info，各含 `-subtle` 变体），以及 spacing / radius / shadow（3 级）/ 字号阶梯 / 动效时长 / z-index 刻度。组件内不再出现魔法值。
- **双主题（深色优先）**：`prefers-color-scheme` 自动深色 + `[data-theme]` 覆盖 + 顶栏切换按钮（写入 `localStorage` 键 `evidenceclass.theme`）。`src/styles/theme.css` 补齐深色表面覆盖。
- **布局骨架**：`AppShell` 侧栏（分组/图标/文字 + 选中左条）、粘性顶栏（面包屑 + 操作）、内容最大宽度；<1024px 抽屉 + 遮罩，<640px 单列。
- **组件打磨**：`StatusBadge` 集中状态→颜色映射；`Metric` 采用 `tabular-nums` + 单位/趋势；表格粘性表头；表单聚焦环 / 错误 / 禁用态；骨架屏 `Skeleton`；`Toast` 通知。
- **微交互与可访问性**：动效 120–220ms 且 `prefers-reduced-motion` 下关闭；语义标签、`aria-current`、`:focus-visible` 2px 环；中文排版行高 1.6–1.7，按钮用语动宾结构。
- 修复根因：原 `main.tsx` 未引入任何 CSS，导致整站无样式；现统一引入 `tokens.css / global.css / theme.css`，构建产物已含 35 kB CSS。

## 结果页真实逻辑梳理

- 结果页通过 `listArtifacts(jobId)` 找到 `analysis_result`（mime `application/json`）产物，拉取 `download_url` 后渲染真实字段（overall、metrics.focus/participation/interaction、evidence、actions），**不再硬编码** `78/100`、`82/67/85`、`EV-042`、`Token 12,480` 等伪值。
- Mock 模式下 `mock.ts` 提供符合 `AnalysisResult` 结构的 `mockAnalysisResult`，E2E 即跑 Mock，不把 Mock 写成 live 证据。
- 轮询使用 TanStack Query `refetchInterval` 回调，命中终态即停并清理；取消任务经 `notifyOnChangeProps` 显式声明依赖以修复 v5 观察器不重渲染问题。
- 统一错误边界：401 → 引导重新登录；每页覆盖 loading / empty / error / normal 四态。

## 当前运行结果

- `npm run build`：通过，输出 `dist/assets/index-*.css` 35.20 kB、`index-*.js` 280.43 kB。
- `npm test`：通过，`src/api/client.test.ts` 2 个用例绿。
- `npm run test:e2e`：通过，10/10 绿（product 5 + responsive 1 + new-pages 4）。

## 跳过项与后续兼容性

以下项目仍明确跳过，但不会阻塞阶段十及后续阶段：

1. **真实 SSE 连续事件与断线重连的浏览器级验收**：客户端 `Last-Event-ID` 接缝和阶段八服务端单测已通过，但仍需带认证的真实 Worker 长连接场景；不能用 Mock 代替。
2. **真实 VLM/远端 OpenAI-compatible 模型效果**：需要有效模型授权和权重；当前远端接口此前返回 403，因此不伪造效果结论。
3. **Qwen 本地环境**：按用户明确要求，本轮不检查、不修改、不运行 Qwen。
4. **像素级视觉走查**：本轮视觉质量通过设计令牌体系 + 构建产物 + E2E 结构/响应式断言验证，未做人工逐页面截图走查；深色主题渲染正确性以 E2E 与构建为准，必要时后续补人工评审。

已解决的离线部分：`scripts/generate-web-openapi.py` 已生成 15 个 TypeScript schema；新建分析页已接入 Job、签名 URL 上传、SHA-256 完成确认；复核按钮已接入 `decideReview` 适配器；取消/重试已接 Toast。真实后端调用只在有认证和基础设施时执行，不把 Mock 结果写成 live 证据。

这些跳过项都保持了稳定的类型和 API 边界，不会把 Mock 数据、未认证请求或未安装的浏览器运行时传递到后续阶段。
