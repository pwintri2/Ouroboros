import { useEffect } from 'react'
import {
  fetchAgentConfig,
  fetchHealth,
  fetchProviders,
  fetchRuntimeStatus,
  fetchStreamStatus,
  mapAgentsToPersonas
} from '../../lib/api'
import { usePersonaStore } from '../../stores/personaStore'
import { useProviderStore } from '../../stores/providerStore'
import { useTelemetryStore } from '../../stores/telemetryStore'
import { SidebarVergadertafel } from '../sidebar/SidebarVergadertafel'
import { RuntimeControlPanel } from '../telemetry/RuntimeControlPanel'
import { TelemetryPanel } from '../telemetry/TelemetryPanel'
import { TopBarEscalation } from '../topbar/TopBarEscalation'
import { WorkspaceHybrid } from '../workspace/WorkspaceHybrid'

export function MissionControlLayout() {
  const mergePersonas = usePersonaStore((state) => state.mergePersonas)
  const patchPersonaStatus = usePersonaStore((state) => state.patchPersonaStatus)
  const setProviderState = useProviderStore((state) => state.setProviderState)
  const setAvailableProviders = useProviderStore((state) => state.setAvailableProviders)
  const upsertSignal = useTelemetryStore((state) => state.upsertSignal)

  useEffect(() => {
    let active = true

    const hydrate = async () => {
      try {
        const config = await fetchAgentConfig()
        if (!active) return
        const personas = mapAgentsToPersonas(config)
        mergePersonas(personas)

        const provider = config.orchestrator.provider === 'gemini' || config.orchestrator.provider === 'groq'
          ? config.orchestrator.provider
          : 'ollama'

        const tier = provider === 'ollama' ? 'tier3-local' : 'tier2-cloud'
        setProviderState(provider, config.orchestrator.model, tier)
      } catch {
        // fallback remains active
      }

      try {
        const providers = await fetchProviders()
        if (!active) return
        setAvailableProviders(providers)
      } catch {
        // keep fallback provider chips
      }

      try {
        const health = await fetchHealth()
        if (!active) return
        upsertSignal({
          id: 'backend-health',
          type: 'main_py',
          value: health.phase || health.status,
          status: health.status === 'ok' || health.status === 'online' ? 'ok' : 'warn',
          source: health.service || health.agent || 'Wintrip Backend',
          timestamp: new Date().toISOString()
        })
      } catch {
        if (!active) return
        upsertSignal({
          id: 'backend-health',
          type: 'main_py',
          value: 'offline',
          status: 'error',
          source: 'Wintrip Backend',
          timestamp: new Date().toISOString()
        })
      }

      try {
        const runtime = await fetchRuntimeStatus()
        if (!active) return
        upsertSignal({
          id: 'sandbox-status',
          type: 'sandbox',
          value: runtime.sandbox.available ? 'ACTIVE' : 'OFFLINE',
          status: runtime.sandbox.available ? 'active' : 'error',
          source: 'Docker Sandbox',
          timestamp: new Date().toISOString()
        })
        upsertSignal({
          id: 'runtime-latency',
          type: 'latency',
          value: runtime.docker_socket ? 'ONLINE' : 'DEGRADED',
          status: runtime.docker_socket ? 'ok' : 'warn',
          source: 'VPS CNS',
          timestamp: new Date().toISOString()
        })
      } catch {
        // runtime endpoint optional during early boot
      }

      try {
        const streamStatus = await fetchStreamStatus()
        if (!active || !streamStatus) return
        upsertSignal({
          id: 'stream-daemon',
          type: 'resonance',
          value: streamStatus.state,
          status: streamStatus.state === 'running' ? 'active' : 'warn',
          source: 'Entanglement Daemon',
          timestamp: new Date().toISOString(),
          meta: streamStatus.stats
        })
      } catch {
        // stream subsystem may not be mounted yet
      }
    }

    void hydrate()
    const interval = window.setInterval(() => {
      void hydrate()
    }, 15000)

    const pulseInterval = window.setInterval(() => {
      const rotating = [
        'wintrip-developer-backend',
        'wintrip-ui-frontend',
        'wintrip-voorzitter-qa-tester',
        'wintrip-kritiek-docs-planning'
      ]
      const pick = rotating[Math.floor(Date.now() / 5000) % rotating.length]
      rotating.forEach((id) => patchPersonaStatus(id, id === pick ? 'observing' : 'idle', id === pick))
    }, 5000)

    return () => {
      active = false
      window.clearInterval(interval)
      window.clearInterval(pulseInterval)
    }
  }, [mergePersonas, patchPersonaStatus, setAvailableProviders, setProviderState, upsertSignal])

  return (
    <div className="blueprint-shell flex h-screen overflow-hidden bg-transparent text-[#2d2418]">
      <SidebarVergadertafel />
      <div className="flex min-w-0 flex-1 flex-col pb-4">
        <TopBarEscalation />
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_290px] gap-3 overflow-hidden px-4 pb-4">
          <WorkspaceHybrid />
          <div className="grid min-h-0 grid-rows-[160px_minmax(0,1fr)] gap-3 overflow-hidden">
            <RuntimeControlPanel />
            <TelemetryPanel />
          </div>
        </div>
      </div>
    </div>
  )
}
