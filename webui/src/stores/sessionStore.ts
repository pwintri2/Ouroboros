import { create } from 'zustand'

interface SessionState {
  sessionId: string | null
  activeThreadId: string
  activeTaskId: string | null
  mode: 'chat' | 'diff' | 'telemetry' | 'hybrid'
  meetingMode: boolean
  yoloEnabled: boolean
  humanApprovalRequired: boolean
  setMode: (mode: SessionState['mode']) => void
  setMeetingMode: (value: boolean) => void
  toggleYolo: () => void
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: null,
  activeThreadId: 'mission-control',
  activeTaskId: null,
  mode: 'hybrid',
  meetingMode: true,
  yoloEnabled: false,
  humanApprovalRequired: true,
  setMode: (mode) => set({ mode }),
  setMeetingMode: (meetingMode) => set({ meetingMode }),
  toggleYolo: () =>
    set((state) => ({
      yoloEnabled: !state.yoloEnabled,
      humanApprovalRequired: state.yoloEnabled
    }))
}))
