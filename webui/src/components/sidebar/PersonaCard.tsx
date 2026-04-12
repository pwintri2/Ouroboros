import { motion } from 'framer-motion'
import type { PersonaCard as PersonaCardType } from '../../types/persona'

const statusColor: Record<PersonaCardType['status'], string> = {
  idle: 'bg-[#b8a48a]',
  thinking: 'bg-[#d4a249]',
  observing: 'bg-[#8da35f]',
  collapsing: 'bg-[#9c7d4e]',
  sandboxing: 'bg-[#c77f4b]',
  blocked: 'bg-[#bb6f57]',
  offline: 'bg-[#9a9488]'
}

const roleGlyph: Record<string, string> = {
  'Wintrip Developer (Backend)': '⌘',
  'Wintrip UI (Frontend)': '◫',
  'Wintrip Voorzitter (QA & Tester)': '◉',
  'Wintrip Kritiek (Docs/Planning)': '✦'
}

export function PersonaCard({
  persona,
  selected,
  onSelect
}: {
  persona: PersonaCardType
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      onClick={onSelect}
      className={`panel-soft w-full p-3 text-left transition hover:bg-[#f4ead7] ${selected ? 'border-[#b88e4a] bg-[#f2e4ca]' : ''}`}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#c7ab81] bg-[#efe2ca] text-sm font-semibold text-[#6e5634]">
          {roleGlyph[persona.name] ?? '◎'}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <div className="truncate text-[13px] font-semibold text-[#342817]">{persona.name}</div>
            <motion.span
              className={`status-dot ${statusColor[persona.status]} ${persona.observerPulse ? 'status-pulse' : ''}`}
              animate={persona.observerPulse ? { scale: [1, 1.15, 1] } : { scale: 1 }}
              transition={{ duration: 1.6, repeat: Infinity }}
            />
          </div>

          <div className="mt-1 truncate text-[11px] uppercase tracking-[0.16em] text-[#876b47]">
            {persona.status === 'idle' ? 'Available' : 'Active'}
          </div>

          <div className="mt-2 truncate text-[11px] text-[#7c6545]">{persona.role}</div>

          <div className="mt-2 flex items-center justify-between text-[11px] text-[#7c6545]">
            <span>{persona.provider}</span>
            <span>{persona.model}</span>
          </div>
        </div>

        <div className="flex flex-col items-center gap-2 text-[#8f6f46]">
          <span className="text-sm">⚙</span>
          <span className="text-sm">👥</span>
        </div>
      </div>
    </button>
  )
}
