import { useState } from 'react'
import { previewCommit, saveCommit } from '../../lib/api'
import { useDiffStore } from '../../stores/diffStore'

export function DiffViewPanel() {
  const diffs = useDiffStore((state) => state.diffs)
  const activeDiffId = useDiffStore((state) => state.activeDiffId)
  const setActiveDiffId = useDiffStore((state) => state.setActiveDiffId)
  const markApplied = useDiffStore((state) => state.markApplied)
  const diff = diffs.find((item) => item.id === activeDiffId) || diffs[0]
  const [previewText, setPreviewText] = useState<string>('')
  const [statusText, setStatusText] = useState<string>('')
  const [busy, setBusy] = useState(false)

  if (!diff) {
    return null
  }

  async function handlePreview() {
    setBusy(true)
    setStatusText('')
    try {
      const result = await previewCommit('mission-control-review.md', diff.after)
      setPreviewText(result.preview)
      setStatusText(result.instruction)
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Preview mislukt.')
    } finally {
      setBusy(false)
    }
  }

  async function handleApply() {
    setBusy(true)
    setStatusText('')
    try {
      const result = await saveCommit('mission-control-review.md', diff.after)
      if (result.status.toLowerCase() === 'success') {
        markApplied(diff.id)
        setStatusText(result.message || 'Bestand opgeslagen in /output/.')
      } else {
        setStatusText(result.detail || 'Opslaan mislukt.')
      }
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Apply mislukt.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel flex h-full flex-col overflow-hidden">
      <div className="border-b border-[#d8c5a8] px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="panel-title">DiffView Staging</div>
            <div className="mt-1 text-xs text-[#7c6545]">Inspect generated code before write approval.</div>
          </div>
          <button className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#ccb28c] bg-[#f5ead5] text-[#755d3d]">
            ⊕
          </button>
        </div>
      </div>

      <div className="border-b border-[#d8c5a8] px-3 py-2">
        <div className="flex gap-2 overflow-auto">
          {diffs.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveDiffId(item.id)}
              className={`rounded-xl border px-3 py-2 text-xs ${item.id === diff.id ? 'border-[#b88e4a] bg-[#f1dfbd] text-[#4d3818]' : 'border-[#ccb28c] bg-[#fbf4e7] text-[#7c6545]'}`}
            >
              {item.sourceAgent}
            </button>
          ))}
        </div>
      </div>

      <div className="flex h-full flex-col p-3">
        <div className="mb-3 flex items-center justify-between gap-3 rounded-xl border border-[#d5c09f] bg-[#fbf4e7] px-3 py-2">
          <div>
            <div className="text-sm font-semibold text-[#342817]">{diff.filePath}</div>
            <div className="mt-1 text-[11px] uppercase tracking-[0.16em] text-[#866b49]">
              {diff.sourceAgent} · {diff.language} · {diff.status}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => void handlePreview()}
              disabled={busy}
              className="blueprint-button disabled:opacity-50"
            >
              Preview
            </button>
            <button
              onClick={() => void handleApply()}
              disabled={busy || diff.status === 'applied'}
              className="blueprint-button-accent disabled:opacity-50"
            >
              {diff.status === 'applied' ? 'Toegepast' : 'Toepassen'}
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden rounded-[16px] border border-[#ccb28c] bg-[#fffaf0]">
          <div className="grid grid-cols-[52px_minmax(0,1fr)] text-xs leading-6 text-[#4e3d26]">
            <div className="border-r border-[#e1d3bc] bg-[#f1e4cc] p-3 text-right text-[#8e7654]">
              {Array.from({ length: 12 }, (_, index) => (
                <div key={index}>{index + 1}</div>
              ))}
            </div>
            <pre className="m-0 h-full overflow-auto p-3 text-[12px] leading-6 text-[#322718]">{diff.unifiedPatch}</pre>
          </div>
        </div>

        {(previewText || statusText) && (
          <div className="mt-3 rounded-[16px] border border-[#ccb28c] bg-[#f8efde] p-3 text-sm text-[#4a3a23]">
            {previewText && (
              <div className="mb-2">
                <div className="tech-label mb-1">Preview</div>
                <pre className="whitespace-pre-wrap text-xs leading-6 text-[#3b2e1b]">{previewText}</pre>
              </div>
            )}
            {statusText && <div>{statusText}</div>}
          </div>
        )}
      </div>
    </section>
  )
}
