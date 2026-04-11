import { ChatStreamPanel } from './ChatStreamPanel'
import { DiffViewPanel } from './DiffViewPanel'
import { StreamStatusCard } from './StreamStatusCard'

export function WorkspaceHybrid() {
  return (
    <main className="grid h-full min-h-0 grid-cols-[minmax(0,1.2fr)_minmax(320px,0.82fr)] gap-3">
      <ChatStreamPanel />
      <div className="grid min-h-0 grid-rows-[minmax(0,1fr)_minmax(180px,0.62fr)] gap-3">
        <DiffViewPanel />
        <StreamStatusCard />
      </div>
    </main>
  )
}
