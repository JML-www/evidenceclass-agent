import React from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { isMockApi, listArtifacts, listAssets, listJobs } from '../../api/client'
import { EmptyState, ErrorState, LoadingState, PageHeader } from '../../components'
import { IconUpload } from '../../components/icons'

type Asset = {
  id: string
  name: string
  type: string
  sizeBytes: number
  uploadedAt: string
}

// Mock 模式下的示例参考材料，仅用于离线演示，不声称来自真实后端。
const SAMPLE_ASSETS: Asset[] = [
  {
    id: 'asset-plan-1',
    name: '高一数学 · 函数单调性 教学计划.pdf',
    type: '教学计划',
    sizeBytes: 248_320,
    uploadedAt: '09-12 10:20',
  },
  {
    id: 'asset-transcript-1',
    name: '课堂转写_函数单调性.srt',
    type: '转写',
    sizeBytes: 18_540,
    uploadedAt: '09-12 10:21',
  },
  {
    id: 'asset-doc-1',
    name: '课程大纲与评测说明.docx',
    type: '课程文档',
    sizeBytes: 92_400,
    uploadedAt: '09-12 10:22',
  },
]

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

export function KnowledgePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const jobsQuery = useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
    enabled: !isMockApi,
  })
  const jobId =
    new URLSearchParams(location.search).get('job_id') ??
    (isMockApi ? 'job_8f21' : jobsQuery.data?.[0]?.id)
  const assetsQuery = useQuery({
    queryKey: ['assets', jobId],
    queryFn: () => listAssets(jobId as string),
    enabled: Boolean(jobId) && !isMockApi,
  })
  const artifactsQuery = useQuery({
    queryKey: ['artifacts', jobId],
    queryFn: () => listArtifacts(jobId as string),
    enabled: Boolean(jobId),
  })

  const assets: Asset[] = isMockApi
    ? SAMPLE_ASSETS
    : ((assetsQuery.data ?? []) as Array<Record<string, unknown>>).map(raw => ({
        id: String(raw.asset_id ?? raw.id ?? ''),
        name: String(raw.name ?? raw.filename ?? '未命名材料'),
        type: String(raw.kind ?? raw.type ?? '参考材料'),
        sizeBytes: Number(raw.size_bytes ?? raw.sizeBytes ?? 0),
        uploadedAt: String(raw.uploaded_at ?? raw.uploadedAt ?? '未知时间'),
      }))

  const hasArtifacts = (artifactsQuery.data ?? []).length > 0

  return (
    <div className="page">
      <PageHeader
        eyebrow="知识库"
        title="知识库"
        description={`已上传的参考材料（教学计划、转写、课程文档）。${jobId ? ` · ${jobId}` : ''}`}
        action={
          <button className="secondary-button" onClick={() => navigate('/new')}>
            <IconUpload size={15} />
            上传新材料
          </button>
        }
      />

      {isMockApi && (
        <div className="success-note" role="status">
          当前为 Mock 模式，展示示例参考材料；接入后端后将读取真实资产列表。
        </div>
      )}

      <section className="panel">
        <div className="panel-toolbar">
          <b>{assets.length} 份参考材料</b>
          <span className="muted">类型 · 大小 · 上传时间</span>
        </div>
        {isMockApi ? (
          <AssetTable assets={assets} />
        ) : assetsQuery.isLoading ? (
          <LoadingState label="正在加载知识库…" />
        ) : assetsQuery.isError ? (
          <ErrorState onRetry={() => assetsQuery.refetch()} />
        ) : assets.length === 0 ? (
          <EmptyState message="还没有上传任何参考材料，先在「新建分析」中附加教学计划或转写。" />
        ) : (
          <AssetTable assets={assets} />
        )}
      </section>

      {hasArtifacts && (
        <section className="panel side-note" style={{ marginTop: 'var(--space-4)' }}>
          <h3 className="section-title">关联产物</h3>
          <p className="muted">
            该分析任务还包含 {artifactsQuery.data?.length}{' '}
            个产物（报告、看板、证据清单等），可在「结果与问答」中查看。
          </p>
        </section>
      )}
    </div>
  )
}

function AssetTable({ assets }: { assets: Asset[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>材料名称</th>
            <th>类型</th>
            <th>大小</th>
            <th>上传时间</th>
          </tr>
        </thead>
        <tbody>
          {assets.map(asset => (
            <tr key={asset.id}>
              <td>
                <b>{asset.name}</b>
              </td>
              <td>
                <span className="tag">{asset.type}</span>
              </td>
              <td className="muted">{formatSize(asset.sizeBytes)}</td>
              <td className="muted">{asset.uploadedAt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
