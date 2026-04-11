import { useState } from 'react'

interface SearchHit {
  text?: string
  metadata?: Record<string, unknown>
}

export function SemanticSearchPanel() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchHit[]>([])
  const [statusText, setStatusText] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSearch() {
    const needle = query.trim()
    if (!needle) return
    setBusy(true)
    setStatusText('')
    try {
      const response = await fetch(`/api/search?q=${encodeURIComponent(needle)}&limit=5`)
      if (!response.ok) {
        throw new Error(`Zoekactie mislukt: ${response.status}`)
      }
      const data = await response.json()
      setResults(data.results || [])
      setStatusText(`${(data.results || []).length} geheugenhits gevonden.`)
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Zoeken mislukt.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mb-3 rounded-[14px] border border-[#ccb28c] bg-[#fbf3e4] p-3 text-sm text-[#5a472d]">
      <div className="tech-label">Hippocampus Search</div>
      <div className="mt-2 flex gap-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Zoek herinneringen..."
          className="min-w-0 flex-1 rounded-xl border border-[#ccb28c] bg-[#fff9ef] px-3 py-2 text-sm text-[#342817] outline-none"
        />
        <button onClick={() => void handleSearch()} disabled={busy} className="blueprint-button disabled:opacity-50">
          Zoek
        </button>
      </div>
      {statusText && <div className="mt-2 text-xs text-[#7d6648]">{statusText}</div>}
      {results.length > 0 && (
        <div className="mt-3 max-h-40 space-y-2 overflow-auto pr-1">
          {results.map((result, index) => (
            <div key={index} className="rounded-xl border border-[#ccb28c] bg-[#fff9ef] px-3 py-2 text-xs text-[#4a3a23]">
              <div>{result.text || 'Geen tekst beschikbaar.'}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
