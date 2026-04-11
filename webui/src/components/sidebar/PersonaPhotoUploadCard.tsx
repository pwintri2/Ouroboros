import { useRef, useState } from 'react'
import { usePersonaStore } from '../../stores/personaStore'

export function PersonaPhotoUploadCard() {
  const [statusText, setStatusText] = useState('')
  const [busy, setBusy] = useState(false)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const selectedPersonaId = usePersonaStore((state) => state.selectedPersonaId)
  const personas = usePersonaStore((state) => state.personas)
  const mergePersonas = usePersonaStore((state) => state.mergePersonas)
  const selectedPersona = personas.find((persona) => persona.id === selectedPersonaId)

  async function handleUpload(file: File) {
    if (!selectedPersonaId) return
    setBusy(true)
    setStatusText('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const response = await fetch(`/api/personas/${selectedPersonaId}/photo`, {
        method: 'POST',
        body: formData
      })
      if (!response.ok) {
        throw new Error(`Photo upload failed: ${response.status}`)
      }
      const data = await response.json()
      const selected = personas.find((persona) => persona.id === selectedPersonaId)
      if (selected) {
        mergePersonas([{ ...selected, photo: data.photo }])
      }
      setStatusText('Foto geüpload.')
    } catch (error) {
      setStatusText(error instanceof Error ? error.message : 'Foto upload mislukt.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mb-3 rounded-[14px] border border-[#ccb28c] bg-[#fbf3e4] p-3 text-sm text-[#5a472d]">
      <div className="tech-label">Persona Photo</div>
      {selectedPersona?.photo && (
        <div className="mt-2 overflow-hidden rounded-xl border border-[#ccb28c] bg-[#fff9ef] p-2">
          <img
            src={`/${selectedPersona.photo}`}
            alt={selectedPersona.name}
            className="h-24 w-full rounded-lg object-cover"
          />
        </div>
      )}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) {
            void handleUpload(file)
          }
        }}
      />
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={!selectedPersonaId || busy}
        className="blueprint-button mt-2 disabled:opacity-50"
      >
        {busy ? 'Uploading...' : 'Upload foto'}
      </button>
      {statusText && <div className="mt-2 text-xs text-[#7d6648]">{statusText}</div>}
    </div>
  )
}
