# EvidenceClass Web

阶段九从零实现的原创 React + TypeScript 工作台。页面、文案、颜色和数据层均为本项目新实现，不读取旧产品的页面资源或 CSS。

## 本地运行

```powershell
Set-Location -LiteralPath "E:\biomedicine\基于大语言模型的课堂学习行为检测赋能平台-王子豪\evidenceclass-agent\apps\web"
npm install
npm run dev
```

默认使用 Mock API，方便在没有 PostgreSQL、Redis、MinIO 时验证 UI 的加载、空、错误和数据状态。接入阶段八 FastAPI 时设置：

```powershell
$env:VITE_USE_MOCK_API = "false"
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000/api/v1"
```

## 验收

```powershell
npm run build
npm run test:e2e
```

核心页面覆盖任务中心、新建分析、Agent Run 时间线、证据浏览器、复核工作台以及结果问答。界面只展示结构化计划、工具摘要和证据，不展示模型私有思维链。
