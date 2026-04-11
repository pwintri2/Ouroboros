export type DiffStatus =
  | 'generated'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'applied'
  | 'failed'

export interface DiffItem {
  id: string
  taskId: string
  sourceAgent: string
  language: 'python' | 'pascal' | 'typescript' | 'html' | 'css' | 'json' | 'mixed'
  filePath: string
  before?: string
  after: string
  unifiedPatch?: string
  status: DiffStatus
  sandboxRef?: string
  outputTarget?: '/output/'
  createdAt: string
}
