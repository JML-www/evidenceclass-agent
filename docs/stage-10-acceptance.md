# 阶段十：报告问答、会话摘要与人工反馈验收

阶段十把结果页的静态问答收口为 Evidence-first 会话闭环：会话和消息按 workspace/job 隔离，回答携带结构化证据或知识 citation；无证据时使用明确的 unavailable fallback。会话摘要只保存有界、脱敏的上下文元数据，并记录版本、哈希和消息范围。人工反馈使用 `review_audits` 保留原始值、修订值、审核理由、审核人、时间和 Evidence ID。

## 本地验收

```powershell
Set-Location -LiteralPath "E:\biomedicine\基于大语言模型的课堂学习行为检测赋能平台-王子豪\evidenceclass-agent"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('evidenceclass-stage10-' + [guid]::NewGuid().ToString() + '.db')
$env:DATABASE_URL = 'sqlite:///' + $tmp.Replace('\','/')
try {
  .\.venv\Scripts\python.exe -m alembic upgrade head
  .\.venv\Scripts\python.exe -m alembic check
  .\.venv\Scripts\python.exe -m alembic downgrade 9aa292a27041
  .\.venv\Scripts\python.exe -m alembic upgrade head
} finally {
  Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
  Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
}

Set-Location -LiteralPath ".\apps\web"
npm test
npm run build
$env:PLAYWRIGHT_BROWSERS_PATH = "E:\playwright-browsers"
npm run test:e2e
```

## 覆盖范围

- 会话创建、列表、读取、消息读取和 `/ask` 结构化回答。
- workspace 与 job 资源级隔离；会话只能读取绑定任务的 EvidenceItem。
- 已授权且已发布的 workspace 知识来源可作为补充 citation；未知/未授权来源不会进入回答。
- 无证据明确拒答，不把 deterministic/mock 结果冒充真实模型。
- 摘要版本、更新时间、哈希、源消息范围和 citation IDs 持久化，摘要不保存媒体路径、联系人或身份信息。
- 反馈支持批准、拒绝、修正和请求材料；空理由、非法 decision、重复提交、跨 job Evidence 和越权 workspace 有稳定错误码。
- 前端 Mock/Real 适配支持发送中、回答成功、证据不足、失败、消息累积和 citation 跳转。

真实远端模型、Qwen、本地未授权模型权重和认证 Worker 的浏览器级 SSE 长连接仍按阶段九约束跳过；这些路径不能用 Mock 代替真实效果。
