import { useState } from 'react'
import { fetchRuntimeStatus, runRuntimeAction } from '../../lib/api'

export function RuntimeControlPanel() {
  const [statusText, setStatusText] = useState('')
  const [dockerLines, setDockerLines] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  async function handleRefresh() {
    setBusy(true)
    try {
      const runtime = await fetchRuntimeStatus()
      setStatusText(`Local runtime ok · orchestrator ${runtime.orchestrator.provider}/${runtime.orchestrator.model} · sandbox ${runtime.sandbox.available ? 'beschikbaar' : 'niet beschikbaar'}`)
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Runtime refresh mislukt.')
    } finally {
      setBusy(false)
    }
  }

  async function handleDockerPs() {
    setBusy(true)
    try {
      const result = await runRuntimeAction('docker_ps')
      setDockerLines(result.output || [])
      setStatusText(result.status === 'ok' ? 'Docker status opgehaald.' : result.detail || 'Docker actie mislukt.')
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Docker actie mislukt.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel flex h-full flex-col p-3">
      <div className="flex items-center justify-between gap-3 border-b border-[#d8c5a8] pb-3">
        <div>
          <div className="panel-title">Local + VPS Control</div>
          <div className="mt-1 text-xs text-[#7c6545]">Quick runtime and container observability.</div>
        </div>
        <div className="rounded-xl border border-[#ccb28c] bg-[#f4e6cb] px-3 py-2 text-[10px] uppercase tracking-[0.16em] text-[#7c6545]">
          Live
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={() => void handleRefresh()}
          disabled={busy}
          className="blueprint-button disabled:opacity-50"
        >
          Refresh Runtime
        </button>
        <button
          onClick={() => void handleDockerPs()}
          disabled={busy}
          className="blueprint-button disabled:opacity-50"
        >
          Docker Status
        </button>
      </div>

      {statusText && <div className="mt-3 text-sm text-[#5a472d]">{statusText}</div>}

      {dockerLines.length > 0 && (
        <pre className="mt-3 flex-1 overflow-auto rounded-[14px] border border-[#ccb28c] bg-[#fff9ef] p-3 text-xs text-[#3c301f]">
          {dockerLines.join('\n')}
        </pre>
      )}
    </section>
  )
}
