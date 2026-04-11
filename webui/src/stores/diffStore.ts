import { create } from 'zustand'
import type { DiffItem } from '../types/diff'

interface DiffState {
  diffs: DiffItem[]
  activeDiffId: string | null
  setDiffs: (diffs: DiffItem[]) => void
  addDiff: (diff: DiffItem) => void
  markApplied: (id: string) => void
  setActiveDiffId: (id: string | null) => void
}

const now = new Date().toISOString()

export const useDiffStore = create<DiffState>((set) => ({
  diffs: [
    {
      id: 'd1',
      taskId: 'WT-UI-001',
      sourceAgent: 'Wintrip UI (Frontend)',
      language: 'typescript',
      filePath: '/app/webui/src/App.tsx',
      after: 'Mission Control shell scaffolded.',
      unifiedPatch: '@@ -0,0 +1,42 @@\n+ Build Mission Control shell',
      status: 'pending_approval',
      outputTarget: '/output/',
      createdAt: now
    }
  ],
  activeDiffId: 'd1',
  setDiffs: (diffs) => set({ diffs, activeDiffId: diffs[0]?.id ?? null }),
  addDiff: (diff) =>
    set((state) => ({
      diffs: [diff, ...state.diffs],
      activeDiffId: diff.id
    })),
  markApplied: (id) =>
    set((state) => ({
      diffs: state.diffs.map((diff) => (diff.id === id ? { ...diff, status: 'applied' } : diff))
    })),
  setActiveDiffId: (activeDiffId) => set({ activeDiffId })
}))
