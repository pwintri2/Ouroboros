import { create } from 'zustand'

interface ProviderState {
  activeProvider: 'ollama' | 'gemini' | 'groq'
  activeModel: string
  tier: 'tier3-local' | 'tier2-cloud' | 'tier1-escalation'
  escalationActive: boolean
  cloudTierEnabled: boolean
  availableProviders: Record<string, { available?: boolean; version?: string; models?: string[] }>
  setProviderState: (provider: ProviderState['activeProvider'], model: string, tier: ProviderState['tier']) => void
  setAvailableProviders: (providers: ProviderState['availableProviders']) => void
  setCloudTierEnabled: (value: boolean) => void
}

export const useProviderStore = create<ProviderState>((set) => ({
  activeProvider: 'gemini',
  activeModel: 'gemini-2.5-pro',
  tier: 'tier2-cloud',
  escalationActive: true,
  cloudTierEnabled: true,
  availableProviders: {},
  setProviderState: (activeProvider, activeModel, tier) =>
    set({
      activeProvider,
      activeModel,
      tier,
      escalationActive: tier !== 'tier3-local'
    }),
  setAvailableProviders: (availableProviders) => set({ availableProviders }),
  setCloudTierEnabled: (cloudTierEnabled) => set({ cloudTierEnabled })
}))
