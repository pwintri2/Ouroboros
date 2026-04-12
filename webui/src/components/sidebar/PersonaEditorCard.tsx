import { useEffect, useState } from 'react'
import { deletePersona, updatePersona } from '../../lib/api'
import { usePersonaStore } from '../../stores/personaStore'

export function PersonaEditorCard() {
  const selectedPersonaId = usePersonaStore((state) => state.selectedPersonaId)
  const personas = usePersonaStore((state) => state.personas)
  const mergePersonas = usePersonaStore((state) => state.mergePersonas)
  const setSelectedPersonaId = usePersonaStore((state) => state.setSelectedPersonaId)
  const [statusText, setStatusText] = useState('')
  const [busy, setBusy] = useState(false)

  const selectedPersona = personas.find((persona) => persona.id === selectedPersonaId)
  const [name, setName] = useState(selectedPersona?.name || '')
  const [description, setDescription] = useState(selectedPersona?.description || '')

  useEffect(() => {
    setName(selectedPersona?.name || '')
    setDescription(selectedPersona?.description || '')
    setStatusText('')
  }, [selectedPersonaId, selectedPersona?.name, selectedPersona?.description])

  if (!selectedPersona || selectedPersona.provider !== 'human') {
    return null
  }

  const currentPersona = selectedPersona

  async function handleSave() {
    setBusy(true)
    setStatusText('')
    try {
      const updated = await updatePersona(currentPersona.id, name.trim(), description.trim())
      mergePersonas([{ ...currentPersona, name: updated.name, description: updated.description || '' }])
      setStatusText('Persona opgeslagen.')
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Opslaan mislukt.')
    } finally {
      setBusy(false)
    }
  }

  async function handleRemove() {
    setBusy(true)
    setStatusText('')
    try {
      await deletePersona(currentPersona.id)
      mergePersonas(personas.filter((persona) => persona.id !== currentPersona.id))
      setSelectedPersonaId(null)
      setStatusText('Persona verwijderd.')
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Verwijderen mislukt.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mb-3 rounded-[14px] border border-[#ccb28c] bg-[#fbf3e4] p-3 text-sm text-[#5a472d]">
      <div className="tech-label">Persona Editor</div>
      <div className="mt-2 grid gap-2">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="rounded-xl border border-[#ccb28c] bg-[#fff9ef] px-3 py-2 text-sm text-[#342817] outline-none"
        />
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="min-h-[72px] resize-none rounded-xl border border-[#ccb28c] bg-[#fff9ef] px-3 py-2 text-sm text-[#342817] outline-none"
        />
        <div className="flex gap-2">
          <button onClick={() => void handleSave()} disabled={busy} className="blueprint-button-accent disabled:opacity-50">
            {busy ? 'Saving...' : 'Opslaan'}
          </button>
          <button onClick={() => void handleRemove()} disabled={busy} className="blueprint-button disabled:opacity-50">
            Verwijderen
          </button>
        </div>
        {statusText && <div className="text-xs text-[#7c6545]">{statusText}</div>}
      </div>
    </div>
  )
}
