import React from 'react'
import { isMockApi } from '../../api/client'
import { InfoBlock, KeyValue, PageHeader } from '../../components'
import { IconShield } from '../../components/icons'

const PRIVACY_BOUNDARIES = [
  '不做学生身份识别（人脸 / 姓名归属）。',
  '不做情绪或心理状态推断。',
  '不做学习能力或成绩归因。',
  '不做医学或发育诊断。',
  '所有结论仅描述可见的可观测课堂行为，并关联到 Evidence。',
]

export function SettingsPage() {
  return (
    <div className="page narrow">
      <PageHeader
        eyebrow="设置"
        title="设置与模型能力"
        description="当前接入的模型、识别能力与隐私边界。能力范围之外的内容不会被声称或推断。"
      />

      <section className="panel settings-section">
        <h3 className="section-title">运行环境</h3>
        <KeyValue label="API 模式" value={isMockApi ? 'Mock（离线示例）' : '真实 API'} />
        <KeyValue label="数据来源" value={isMockApi ? '前端内置示例数据' : '阶段八后端服务'} />
        <KeyValue label="评测结果端点" value="未接入（需 scripts/accept-stage-11.ps1）" />
      </section>

      <section className="panel settings-section">
        <h3 className="section-title">模型能力边界</h3>
        <KeyValue label="语言模型" value="本地 Qwen3.5-0.8B" />
        <KeyValue label="Provider" value="local-qwen-temporary" />
        <KeyValue label="语音识别 (ASR)" value="本地 FunASR" />
        <KeyValue label="文字识别 (OCR)" value="RapidOCR" />
        <KeyValue label="远端付费模型" value="未接入" />
      </section>

      <section className="panel settings-section">
        <h3 className="section-title">
          <IconShield size={15} />
          隐私与边界
        </h3>
        <div className="boundary-list">
          {PRIVACY_BOUNDARIES.map(item => (
            <div className="boundary-item" key={item}>
              <span className="boundary-dot" />
              {item}
            </div>
          ))}
        </div>
        <InfoBlock
          title="关于能力声明"
          text="当前模型仅用于生成可核查的课堂行为观察；凡超出上述边界的推断均不会发生，报告也不会包含身份、情绪、能力或诊断结论。"
          muted
        />
      </section>
    </div>
  )
}
