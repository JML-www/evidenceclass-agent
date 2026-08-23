# Feature boundaries

阶段九首轮将页面组件集中在 `src/app/App.tsx`，以保证一次性完成工作流并减少跨文件改动。页面已经按以下 feature 边界命名，阶段十可直接拆分而不改变 API 契约：`jobs`、`agent-runs`、`evidence`、`reviews`、`knowledge`、`evaluations`。
