import { useMemo, useState } from 'react'
import { switchModel } from '../../lib/api'
import { useProviderStore } from '../../stores/providerStore'
import { useSessionStore } from '../../stores/sessionStore'

const fallbackPresets = [
  { provider: 'gemini' as const, model: 'gemini-2.5-pro', paid: true },
  { provider: 'ollama' as const, model: 'gemma4:latest', paid: false },
  { provider: 'groq' as const, model: 'llama-3.3-70b-versatile', paid: true }
]

export function TopBarEscalation() {
  const {
    activeProvider,
    activeModel,
    tier,
    escalationActive,
    cloudTierEnabled,
    availableProviders,
    setProviderState,
    setCloudTierEnabled
  } = useProviderStore()
  const { yoloEnabled, toggleYolo } = useSessionStore()
  const [busy, setBusy] = useState(false)
  const [statusText, setStatusText] = useState('')

  const modelOptions = useMemo(() => {
    const dynamic = Object.entries(availableProviders).flatMap(([provider, meta]) =>
      (meta.models || []).map((model) => ({
        provider: (provider === 'gemini' || provider === 'groq' ? provider : 'ollama') as 'gemini' | 'ollama' | 'groq',
        model,
        paid: provider !== 'ollama'
      }))
    )

    const merged = [...fallbackPresets]
    dynamic.forEach((entry) => {
      if (!merged.some((item) => item.provider === entry.provider && item.model === entry.model)) {
        merged.push(entry)
      }
    })
    return merged
  }, [availableProviders])

  const activePreset = modelOptions.find((preset) => preset.provider === activeProvider && preset.model === activeModel)
    || fallbackPresets.find((preset) => preset.provider === activeProvider)
    || fallbackPresets[0]

  const cloudWarning = activePreset.paid ? 'API / kosten actief' : 'Lokaal / geen API-kosten'
  const costGlow = activePreset.paid ? 'border-[#c16d58] bg-[#e9d1c2] text-[#7b3328]' : 'border-[#bca27e] bg-[#f6eddd] text-[#4f3a1f]'

  async function handleSwitch(provider: 'gemini' | 'ollama' | 'groq', model: string) {
    setBusy(true)
    setStatusText('')
    try {
      const result = await switchModel(model, provider)
      const nextTier = provider === 'ollama' ? 'tier3-local' : provider === 'groq' ? 'tier1-escalation' : 'tier2-cloud'
      setProviderState(provider, result.active_model, nextTier)
      setStatusText(`Actief model: ${result.active_model} via ${result.provider}`)
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Model wisselen mislukt.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <header className="panel mx-4 mt-4 flex h-[96px] items-center justify-between rounded-[22px] px-5 py-3">
      <div className="flex min-w-0 flex-1 items-center gap-4">
        <div className="panel-soft flex min-w-0 flex-1 items-center gap-4 px-4 py-3">
          <div className="text-sm text-[#8d7149]">⌘</div>
          <div className="min-w-0 flex-1">
            <div className="tech-label">Top Bar: Model Selection</div>
            <div className="mt-1 flex min-w-0 items-center gap-3">
              <select
                value={`${activeProvider}:${activeModel}`}
                onChange={(event) => {
                  const parts = event.target.value.split(':')
                  const provider = parts.shift() as 'gemini' | 'ollama' | 'groq'
                  const model = parts.join(':')
                  void handleSwitch(provider, model)
                }}
                className="min-w-0 flex-1 rounded-xl border border-[#c6ab83] bg-[#fbf5e8] px-3 py-2 text-sm text-[#372918] outline-none"
              >
                {modelOptions.map((preset) => (
                  <option key={`${preset.provider}:${preset.model}`} value={`${preset.provider}:${preset.model}`}>
                    {preset.model} {preset.paid ? '• Cloud' : '• Local'}
                  </option>
                ))}
              </select>

              <div className={`rounded-xl border px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] ${costGlow}`}>
                {activePreset.paid ? 'Cloud Cost' : 'Local Free'}
              </div>
            </div>
            <div className={`mt-2 text-[11px] ${activePreset.paid ? 'text-[#8d3e35]' : 'text-[#7c6545]'}`}>
              {cloudWarning}
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setCloudTierEnabled(!cloudTierEnabled)}
          className={`panel-soft flex items-center gap-3 px-4 py-3 ${cloudTierEnabled ? 'border-[#c79c59] bg-[#f0dfba]' : ''}`}
        >
          <span className="tech-label">Cloud Tier 1</span>
          <span className={`status-dot ${cloudTierEnabled ? 'bg-[#c09047]' : 'bg-[#c9b8a1]'}`} />
        </button>

        <button
          type="button"
          onClick={toggleYolo}
          className={`panel-soft flex items-center gap-3 px-4 py-3 ${yoloEnabled ? 'border-[#c09047] bg-[#f0dfba]' : ''}`}
        >
          <span className="tech-label">YOLO</span>
          <span className={`relative inline-flex h-6 w-11 items-center rounded-full border border-[#b99d73] ${yoloEnabled ? 'bg-[#d7b16d]' : 'bg-[#e7ddcb]'}`}>
            <span className={`inline-block h-4 w-4 transform rounded-full bg-[#fff7ea] transition ${yoloEnabled ? 'translate-x-6' : 'translate-x-1'}`} />
          </span>
        </button>
      </div>

      <div className="ml-4 min-w-[210px] text-right">
        <div className="tech-label">Confidential / Escalation</div>
        <div className={`mt-1 text-xs ${escalationActive ? 'text-[#8d3e35]' : 'text-[#7c6545]'}`}>Tier: {tier}</div>
        <div className="mt-1 text-[11px] text-[#8d7149]">{busy ? 'Switching model...' : statusText || `${activeProvider} · ${activeModel}`}</div>
      </div>
    </header>
  )
}
