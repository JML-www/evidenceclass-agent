import React from 'react'
import { InfoBlock, PageHeader } from '../../components'

// 数据集定义来自 evals/datasets/manifest.v1.json（参考内容，非评测指标）。
const DATASETS = [
  {
    key: 'perception',
    name: '感知',
    enName: 'perception',
    records: 52,
    description: '课堂视觉与音频可观测信号：注意力、互动、身体朝向等可直接标注的事实。',
  },
  {
    key: 'retrieval',
    name: '检索',
    enName: 'retrieval',
    records: 40,
    description: '证据召回与引用准确性：给定观察能否回到正确的原始帧 / ASR 片段。',
  },
  {
    key: 'agent',
    name: 'Agent',
    enName: 'agent',
    records: 50,
    description: '端到端任务执行与决策：规划、工具调用、复核建议的合理性。',
  },
] as const

const METRIC_DEFINITIONS = [
  { name: '证据可追溯率', description: '结论能关联到一个具体 Evidence ID 的比例。' },
  { name: '确定性覆盖率', description: '观察结论附带确定性结果（非纯 LLM 解释）的比例。' },
  { name: '引用准确率', description: '检索数据集中引用指向正确原始材料的比例。' },
  { name: '复核一致性', description: '人工复核与模型建议一致的案例比例。' },
]

export function EvaluationPage() {
  return (
    <div className="page">
      <PageHeader
        eyebrow="EVALUATION"
        title="评测中心"
        description="基于可观测标签的离线评测数据集与评测口径说明。"
      />
      <div className="metric-grid">
        {DATASETS.map(dataset => (
          <div className="metric-card tone-purple" key={dataset.key}>
            <span className="metric-icon">◈</span>
            <div>
              <span>
                {dataset.name} · {dataset.enName}
              </span>
              <strong>{dataset.records}</strong>
              <small>条样本</small>
            </div>
          </div>
        ))}
      </div>

      <section className="panel eval-section">
        <div className="panel-toolbar">
          <h2>数据集</h2>
          <span className="muted">合成数据 · 已授权 · 不含隐私资产</span>
        </div>
        {DATASETS.map(dataset => (
          <div className="eval-dataset" key={dataset.key}>
            <div className="eval-dataset-head">
              <b>
                {dataset.name}（{dataset.enName}）
              </b>
              <span className="tag">{dataset.records} 条</span>
            </div>
            <p>{dataset.description}</p>
          </div>
        ))}
        <div className="eval-meta">
          切分：训练 70% / 测试 30% · 标签 schema：observable-classroom-labels.v1 ·
          评测器：stage-11-evaluators.v1 · 生成于 2026-09-09
        </div>
      </section>

      <section className="panel eval-section">
        <div className="panel-toolbar">
          <h2>指标定义</h2>
        </div>
        {METRIC_DEFINITIONS.map(metric => (
          <InfoBlock
            key={metric.name}
            title={metric.name}
            text={metric.description}
          />
        ))}
      </section>

      <section className="panel eval-section callout">
        <span>ⓘ</span>
        <div>
          <b>最近一次评测结果</b>
          <p>
            本地评测报告，需通过 <code>scripts/accept-stage-11.ps1</code> 生成。
            当前前端未接入评测结果端点，因此不展示任何评测指标数字，避免编造结论。
          </p>
        </div>
      </section>
    </div>
  )
}
