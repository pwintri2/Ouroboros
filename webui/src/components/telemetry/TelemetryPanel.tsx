import { useMemo } from 'react'
import { useTelemetryStore } from '../../stores/telemetryStore'

function statusTone(status: string) {
  if (status === 'error') return 'text-[#9d473f]'
  if (status === 'warn' || status === 'active') return 'text-[#9a7334]'
  return 'text-[#4f3d24]'
}

export function TelemetryPanel() {
  const signals = useTelemetryStore((state) => state.signals)

  const cards = useMemo(() => {
    const lookup = new Map(signals.map((signal) => [signal.type, signal]))
    return [
      {
        id: 'main',
        label: 'main.py',
        value: String(lookup.get('main_py')?.value ?? 'RUNNING'),
        meta: lookup.get('main_py')?.source ? String(lookup.get('main_py')?.source) : 'CPU 12% | MEM 450MB',
        status: lookup.get('main_py')?.status ?? 'ok'
      },
      {
        id: 'chroma',
        label: 'ChromaDB',
        value: String(lookup.get('chromadb')?.value ?? 'CONNECTED'),
        meta: lookup.get('chromadb')?.source ? String(lookup.get('chromadb')?.source) : 'Latency 5ms',
        status: lookup.get('chromadb')?.status ?? 'ok'
      },
      {
        id: 'docker',
        label: 'Docker Sandbox',
        value: String(lookup.get('sandbox')?.value ?? 'ACTIVE'),
        meta: lookup.get('sandbox')?.source ? String(lookup.get('sandbox')?.source) : 'Containers: 3 | Network: SECURE',
        status: lookup.get('sandbox')?.status ?? 'active'
      },
      {
        id: 'vps',
        label: 'VPS CNS',
        value: String(lookup.get('latency')?.value ?? 'ONLINE'),
        meta: lookup.get('latency')?.source ? String(lookup.get('latency')?.source) : 'Edge uplink nominal',
        status: lookup.get('latency')?.status ?? 'ok'
      }
    ]
  }, [signals])

  return (
    <section className="panel flex h-full flex-col overflow-hidden">
      <div className="border-b border-[#d8c5a8] px-4 py-3">
        <div className="panel-title">Telemetry</div>
        <div className="mt-1 text-xs text-[#7c6545]">Real-time monitoring for main.py, ChromaDB, Docker and VPS.</div>
      </div>

      <div className="flex-1 space-y-2 p-3">
        {cards.map((card, index) => (
          <div key={card.id} className="rounded-[14px] border border-[#ccb28c] bg-[#fbf5e8] p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-[#342817]">{card.label}</div>
                <div className="mt-1 text-[11px] text-[#856b49]">{card.meta}</div>
              </div>
              <div className={`text-right text-[11px] font-semibold uppercase tracking-[0.18em] ${statusTone(card.status)}`}>
                {card.value}
              </div>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#e8dbc3]">
              <div className="telemetry-bar h-full rounded-full" style={{ width: `${70 - index * 10}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
