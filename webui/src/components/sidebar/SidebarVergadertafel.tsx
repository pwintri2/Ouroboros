import { useEffect, useMemo, useState } from 'react'
import { fetchPersonas, fetchTableState } from '../../lib/api'
import { usePersonaStore } from '../../stores/personaStore'
import { ChatHistoryPanel } from './ChatHistoryPanel'
import { MeetingTableControls } from './MeetingTableControls'
import { PersonaCard } from './PersonaCard'
import { PersonaManagerCard } from './PersonaManagerCard'
import { PersonaPhotoUploadCard } from './PersonaPhotoUploadCard'
import { SemanticSearchPanel } from './SemanticSearchPanel'

const railIcons = ['◧', '⌘', '✎', '☰', '⌂', '⚙']

export function SidebarVergadertafel() {
  const [query, setQuery] = useState('')
  const personas = usePersonaStore((state) => state.personas)
  const selectedPersonaId = usePersonaStore((state) => state.selectedPersonaId)
  const setSelectedPersonaId = usePersonaStore((state) => state.setSelectedPersonaId)
  const mergePersonas = usePersonaStore((state) => state.mergePersonas)
  const setSeatedPersonaIds = usePersonaStore((state) => state.setSeatedPersonaIds)

  useEffect(() => {
    let active = true
    fetchPersonas()
      .then((items) => {
        if (!active || !items.length) return
        mergePersonas(
          items.map((item) => ({
            id: item.id,
            name: item.name,
            role: 'Custom persona',
            provider: 'human' as const,
            model: 'persona',
            tier: 'human' as const,
            status: 'idle' as const,
            observerPulse: false,
            description: item.description || '',
            photo: item.photo || null
          }))
        )
      })
      .catch(() => {
        // persona API optional
      })

    fetchTableState()
      .then((state) => {
        if (!active) return
        setSeatedPersonaIds(state.seated || [])
      })
      .catch(() => {
        // table state optional during startup
      })

    return () => {
      active = false
    }
  }, [mergePersonas, setSeatedPersonaIds])

  const activeCount = useMemo(
    () => personas.filter((persona) => persona.status !== 'idle' && persona.status !== 'offline').length,
    [personas]
  )

  const filteredPersonas = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return personas
    return personas.filter((persona) => {
      return (
        persona.name.toLowerCase().includes(needle) ||
        persona.role.toLowerCase().includes(needle) ||
        (persona.model || '').toLowerCase().includes(needle) ||
        (persona.description || '').toLowerCase().includes(needle)
      )
    })
  }, [personas, query])

  const selectedPersona = personas.find((persona) => persona.id === selectedPersonaId) ?? null

  return (
    <aside className="flex h-full w-[350px] gap-3 p-4 pr-0">
      <div className="blueprint-rail flex w-[46px] flex-col items-center justify-between px-2 py-3">
        <div className="flex flex-col items-center gap-3">
          {railIcons.slice(0, 4).map((icon, index) => (
            <button
              key={`${icon}-${index}`}
              className="flex h-8 w-8 items-center justify-center rounded-xl border border-[#c7ad84] bg-[#f8efde] text-[13px] text-[#6a5230]"
            >
              {icon}
            </button>
          ))}
        </div>
        <div className="flex flex-col items-center gap-3">
          {railIcons.slice(4).map((icon, index) => (
            <button
              key={`${icon}-${index}`}
              className="flex h-8 w-8 items-center justify-center rounded-xl border border-[#c7ad84] bg-[#f8efde] text-[13px] text-[#6a5230]"
            >
              {icon}
            </button>
          ))}
        </div>
      </div>

      <div className="panel flex min-w-0 flex-1 flex-col p-3">
        <div className="mb-3 flex items-start justify-between gap-3 border-b border-[#d7c4a6] pb-3">
          <div>
            <div className="panel-title">The Meeting Table</div>
            <div className="mt-2 text-lg font-semibold text-[#302517]">Mission Control</div>
            <div className="mt-1 text-xs text-[#7f684b]">Active agents, personas and swarm roles.</div>
          </div>
          <div className="rounded-xl border border-[#ccb28c] bg-[#f3e5c9] px-3 py-2 text-right">
            <div className="text-[10px] uppercase tracking-[0.2em] text-[#98764c]">Active</div>
            <div className="mt-1 text-lg font-semibold text-[#3d2e1a]">{activeCount}</div>
          </div>
        </div>

        <div className="mb-3 flex items-center gap-2">
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search chats, personas, memories..."
            className="min-w-0 flex-1 rounded-xl border border-[#ccb28c] bg-[#fbf5e8] px-3 py-2 text-sm text-[#342817] outline-none placeholder:text-[#9b825f]"
          />
          <button className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#ccb28c] bg-[#f8efde] text-[#72583a]">
            ⌕
          </button>
        </div>

        <ChatHistoryPanel />
        <SemanticSearchPanel />
        <PersonaManagerCard />
        <PersonaPhotoUploadCard />
        <MeetingTableControls />

        {selectedPersona && (
          <div className="mb-3 rounded-[14px] border border-[#ccb28c] bg-[#fbf3e4] p-3 text-sm text-[#5a472d]">
            <div className="tech-label">Selected Persona</div>
            <div className="mt-1 font-semibold text-[#342817]">{selectedPersona.name}</div>
            <div className="mt-1 text-xs text-[#7d6648]">{selectedPersona.description || selectedPersona.role}</div>
            {selectedPersona.photo && <div className="mt-2 text-xs text-[#7d6648]">Foto: {selectedPersona.photo}</div>}
          </div>
        )}

        <div className="flex-1 space-y-2 overflow-auto pr-1">
          {filteredPersonas.map((persona) => (
            <PersonaCard
              key={persona.id}
              persona={persona}
              selected={persona.id === selectedPersonaId}
              onSelect={() => setSelectedPersonaId(persona.id)}
            />
          ))}
        </div>
      </div>
    </aside>
  )
}
