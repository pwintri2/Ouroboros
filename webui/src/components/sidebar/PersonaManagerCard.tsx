import { useState } from 'react'
import { createPersona } from '../../lib/api'
import { usePersonaStore } from '../../stores/personaStore'

export function PersonaManagerCard() {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [statusText, setStatusText] = useState('')
  const [busy, setBusy] = useState(false)
  const personas = usePersonaStore((state) => state.personas)
  const setPersonas = usePersonaStore((state) => state.setPersonas)
  const setSelectedPersonaId = usePersonaStore((state) => state.setSelectedPersonaId)

  async function handleCreate() {
    const trimmed = name.trim()
    if (!trimmed || busy) return

    setBusy(true)
    setStatusText('')
    try {
      const created = await createPersona(trimmed, description.trim())
      const nextPersona = {
        id: created.id,
        name: created.name,
        role: 'Custom persona',
        provider: 'human' as const,
        model: 'persona',
        tier: 'human' as const,
        status: 'idle' as const,
        observerPulse: false,
        description: created.description || '',
        photo: created.photo || null
      }
      setPersonas([nextPersona, ...personas])
      setSelectedPersonaId(created.id)
      setName('')
      setDescription('')
      setStatusText('Persona aangemaakt.')
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Persona aanmaken mislukt.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mb-3 rounded-[14px] border border-[#ccb28c] bg-[#fbf3e4] p-3 text-sm text-[#5a472d]">
      <div className="tech-label">Persona Manager</div>
      <div className="mt-2 grid gap-2">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Naam nieuwe persona"
          className="rounded-xl border border-[#ccb28c] bg-[#fff9ef] px-3 py-2 text-sm text-[#342817] outline-none"
        />
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Instructieprompt / beschrijving"
          className="min-h-[72px] resize-none rounded-xl border border-[#ccb28c] bg-[#fff9ef] px-3 py-2 text-sm text-[#342817] outline-none"
        />
        <button
          onClick={() => void handleCreate()}
          disabled={busy}
          className="blueprint-button-accent disabled:opacity-50"
        >
          {busy ? 'Creating...' : 'Persona toevoegen'}
        </button>
        {statusText && <div className="text-xs text-[#7c6545]">{statusText}</div>}
      </div>
    </div>
  )
}
