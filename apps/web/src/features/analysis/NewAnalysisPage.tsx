import React from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  completeUpload,
  createJob,
  initUpload,
  isMockApi,
  sha256Hex,
  startJob,
  uploadToSignedUrl,
} from '../../api/client'
import type { Job } from '../../types'
import { PageHeader } from '../../components'
import {
  IconCheck,
  IconCheckCircle,
  IconImage,
  IconLayers,
  IconNew,
  IconSend,
  IconShield,
  IconUpload,
  IconVideo,
} from '../../components/icons'
import { useToast } from '../../components/Toast'
import { modeText } from '../../lib/constants'

const FLOW_STEPS = [
  '媒体校验与抽帧',
  'ASR / OCR / 视觉观察',
  '证据校验与报告生成',
  '人工复核与结果导出',
]
const FLOW_HINTS = ['约 10 秒', '按素材时长', '自动执行', '可选']

const MODE_DESC: Record<Job['mode'], string> = {
  VIDEO: '抽帧、ASR 与行为观察',
  IMAGE: '板书或课堂快照',
  STRUCTURED: '直接提交结构化特征',
}

const MODE_ACCEPT: Record<Job['mode'], string> = {
  VIDEO: 'video/*',
  IMAGE: 'image/*',
  STRUCTURED: '.json,.csv',
}

const MODE_HINT: Record<Job['mode'], string> = {
  VIDEO: 'MP4、MOV，最大 2GB',
  IMAGE: 'PNG、JPG，最大 20MB',
  STRUCTURED: 'JSON、CSV，最大 10MB',
}

function ModeIcon({ mode }: { mode: Job['mode'] }) {
  if (mode === 'VIDEO') return <IconVideo size={16} />
  if (mode === 'IMAGE') return <IconImage size={16} />
  return <IconLayers size={16} />
}

export function NewAnalysisPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()
  const [mode, setMode] = React.useState<Job['mode']>('VIDEO')
  const [title, setTitle] = React.useState('')
  const [file, setFile] = React.useState<File | null>(null)
  const [contextFile, setContextFile] = React.useState<File | null>(null)
  const [progress, setProgress] = React.useState(0)
  const [submitted, setSubmitted] = React.useState(false)
  const [submitError, setSubmitError] = React.useState('')

  const uploadFile = async (
    jobId: string,
    uploadFileValue: File,
    role: string,
    onProgress?: (value: number) => void,
  ) => {
    const ticket = await initUpload(
      jobId,
      uploadFileValue.type || 'application/octet-stream',
      uploadFileValue.size,
      role,
    )
    await uploadToSignedUrl(String(ticket.upload_url ?? ''), uploadFileValue, onProgress)
    await completeUpload(
      jobId,
      String(ticket.upload_id),
      uploadFileValue.size,
      await sha256Hex(uploadFileValue),
    )
  }

  const LIMIT_BYTES: Record<Job['mode'], number> = {
    VIDEO: 2 * 1024 * 1024 * 1024,
    IMAGE: 20 * 1024 * 1024,
    STRUCTURED: 10 * 1024 * 1024,
  }
  const fileTooLarge = file && file.size > LIMIT_BYTES[mode]

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setSubmitted(true)
    setSubmitError('')
    setProgress(0)
    if (!isMockApi && !file) {
      setSubmitted(false)
      setSubmitError('请选择媒体文件')
      return
    }
    if (fileTooLarge) {
      setSubmitted(false)
      setSubmitError(
        `文件超过当前模式上限（${(LIMIT_BYTES[mode] / 1024 / 1024).toFixed(0)} MB），请压缩后重试。`,
      )
      return
    }
    try {
      const job = await createJob(title || '未命名课堂分析', mode)
      if (file && !isMockApi) {
        await uploadFile(job.id, file, 'source', setProgress)
        if (contextFile) await uploadFile(job.id, contextFile, 'context')
      } else {
        for (let value = 10; value <= 100; value += 10) {
          await new Promise(resolve => setTimeout(resolve, 30))
          setProgress(value)
        }
      }
      await startJob(job.id)
      await queryClient.invalidateQueries({ queryKey: ['jobs'] })
      toast.notify('分析任务已创建并开始执行', 'success')
      navigate(`/runs/${job.id}`)
    } catch (error) {
      setSubmitted(false)
      setSubmitError(error instanceof Error ? error.message : '创建分析失败')
      toast.notify(`创建失败：${error instanceof Error ? error.message : '未知错误'}`, 'danger')
    }
  }

  return (
    <div className="page narrow">
      <PageHeader
        eyebrow="新建分析"
        title="新建分析"
        description="上传课堂素材，Agent 会生成带时间戳的可核查证据。"
      />

      <form className="form-layout" onSubmit={submit}>
        <section className="panel form-panel">
          <h2>选择分析模式</h2>
          <div className="mode-cards">
            {(['VIDEO', 'IMAGE', 'STRUCTURED'] as const).map(value => (
              <button
                type="button"
                key={value}
                className={mode === value ? 'mode-card selected' : 'mode-card'}
                aria-pressed={mode === value}
                onClick={() => {
                  setMode(value)
                  setFile(null)
                }}
              >
                <span className="mode-icon">
                  <ModeIcon mode={value} />
                </span>
                <span>
                  <b>{modeText[value]}</b>
                  <small>{MODE_DESC[value]}</small>
                </span>
                {mode === value && (
                  <span className="check">
                    <IconCheck size={14} />
                  </span>
                )}
              </button>
            ))}
          </div>

          <label className="field-label" htmlFor="title">
            分析名称<span>（可选）</span>
          </label>
          <input
            id="title"
            value={title}
            onChange={event => setTitle(event.target.value)}
            placeholder="例如：高一数学 · 函数单调性"
          />

          <label className="field-label" htmlFor="media">
            上传媒体
          </label>
          <label className={file ? 'dropzone has-file' : 'dropzone'} htmlFor="media">
            <input
              id="media"
              type="file"
              accept={MODE_ACCEPT[mode]}
              onChange={event => setFile(event.target.files?.[0] ?? null)}
            />
            {file ? (
              <>
                <span className="upload-icon success">
                  <IconCheckCircle size={22} />
                </span>
                <b>{file.name}</b>
                <small>{(file.size / 1024 / 1024).toFixed(2)} MB · 已就绪</small>
              </>
            ) : (
              <>
                <span className="upload-icon">
                  <IconUpload size={22} />
                </span>
                <b>拖拽文件到这里，或点击选择</b>
                <small>支持 {MODE_HINT[mode]}</small>
              </>
            )}
          </label>

          <label className="field-label" htmlFor="context-media">
            教学计划或转写<span>（可选）</span>
          </label>
          <label
            className={contextFile ? 'dropzone compact has-file' : 'dropzone compact'}
            htmlFor="context-media"
          >
            <input
              id="context-media"
              type="file"
              accept=".pdf,.doc,.docx,.txt,.srt,.vtt,.json"
              onChange={event => setContextFile(event.target.files?.[0] ?? null)}
            />
            {contextFile ? (
              <>
                <span className="upload-icon success">
                  <IconCheckCircle size={20} />
                </span>
                <b>{contextFile.name}</b>
                <small>辅助语境材料 · 已就绪</small>
              </>
            ) : (
              <>
                <span className="upload-icon">
                  <IconNew size={20} />
                </span>
                <b>添加教学计划、讲义或转写</b>
                <small>可选，用于补充分析语境</small>
              </>
            )}
          </label>

          {submitted && (
            <div className="upload-progress">
              <div className="progress-track">
                <span style={{ width: `${progress}%` }} />
              </div>
              <small>{progress < 100 ? `上传中 ${progress}%` : '上传完成'}</small>
            </div>
          )}

          {submitError && (
            <div className="form-error" role="alert">
              {submitError}
            </div>
          )}

          <div className="privacy-note">
            <span>
              <IconShield size={16} />
            </span>
            <p>
              <b>隐私与能力边界</b>
              <br />
              媒体默认仅保存在当前工作区。模型输出是辅助观察，不等同于对学生的诊断；所有报告结论都必须关联
              Evidence。
            </p>
          </div>

          <button className="primary-button submit-button" type="submit" disabled={submitted}>
            {submitted ? (
              '正在创建任务…'
            ) : (
              <>
                开始分析
                <IconSend size={15} />
              </>
            )}
          </button>
        </section>

        <aside className="panel side-note">
          <h3>分析流程</h3>
          {FLOW_STEPS.map((step, index) => (
            <div className="flow-step" key={step}>
              <span>{index + 1}</span>
              <p>
                {step}
                <small>{FLOW_HINTS[index]}</small>
              </p>
            </div>
          ))}
        </aside>
      </form>
    </div>
  )
}
