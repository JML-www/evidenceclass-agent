# 阶段十一：AI/RAG/Agent 评测开发日志

## 2026-09-09

- 核对阶段十基线：`4213fd5`，保留工作区已有未提交的前端/API/worker 接续改动。
- 新增 annotation manual、data card、dataset manifest 和授权合成 JSONL fixture。
- 新增 perception evaluator：30 visual、ASR 分类 CER、OCR slide/board/no_text、结构契约指标。
- 新增 retrieval evaluator：Recall@5、MRR、nDCG@5、citation precision/recall、groundedness、拒答和 workspace leak。
- 新增 50-case Agent schema/evaluator，覆盖无音频、缺能力、工具失败、人工复核和证据边界字段。
- 新增 `evals/run_stage11_eval.py` 与 `scripts/accept-stage-11.ps1`，输出 JSON/Markdown 到被忽略的 `runs/`。
- 离线 deterministic baseline 已通过：visual=30、retrieval=40、agent=50；真实 VLM/ASR/OCR/LLM 因无显式授权列为 skipped，未冒充真实准确率。

