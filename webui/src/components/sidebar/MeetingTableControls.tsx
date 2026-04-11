import { invitePersona, removePersona } from '../../lib/api'
import { usePersonaStore } from '../../stores/personaStore'

export function MeetingTableControls() {
  const selectedPersonaId = usePersonaStore((state) => state.selectedPersonaId)
  const seatedPersonaIds = usePersonaStore((state) => state.seatedPersonaIds)
  const setSeatedPersonaIds = usePersonaStore((state) => state.setSeatedPersonaIds)

  const seated = selectedPersonaId ? seatedPersonaIds.includes(selectedPersonaId) : false

  async function handleInvite() {
    if (!selectedPersonaId) return
    const result = await invitePersona(selectedPersonaId)
    setSeatedPersonaIds(result.seated)
  }

  async function handleRemove() {
    if (!selectedPersonaId) return
    const result = await removePersona(selectedPersonaId)
    setSeatedPersonaIds(result.seated)
  }

  return (
    <div className="mb-3 rounded-[14px] border border-[#ccb28c] bg-[#fbf3e4] p-3 text-sm text-[#5a472d]">
      <div className="tech-label">Vergadertafel</div>
      <div className="mt-2 flex gap-2">
        <button onClick={() => void handleInvite()} disabled={!selectedPersonaId || seated} className="blueprint-button disabled:opacity-50">
          Uitnodigen
        </button>
        <button onClick={() => void handleRemove()} disabled={!selectedPersonaId || !seated} className="blueprint-button disabled:opacity-50">
          Verwijderen
        </button>
      </div>
      <div className="mt-2 text-xs text-[#7d6648]">Seated persona ids: {seatedPersonaIds.join(', ') || 'geen'}</div>
    </div>
  )
}
