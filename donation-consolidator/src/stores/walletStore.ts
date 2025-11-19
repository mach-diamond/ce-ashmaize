import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface RegisteredAddress {
  address: string
  validatedChallenges: number
  donationSent: boolean
  donationSignature?: string
  lastUpdated?: string
}

const STORAGE_KEY = 'midnight-donation-tracker'

export const useWalletStore = defineStore('wallet', () => {
  // State
  const connectedWallet = ref<string | null>(null)
  const connectedAddresses = ref<string[]>([])
  const registeredAddresses = ref<RegisteredAddress[]>([])
  const donationAddress = ref<string>('')
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Computed
  const isConnected = computed(() => connectedAddresses.value.length > 0)
  
  const matchedAddresses = computed(() => {
    if (connectedAddresses.value.length === 0) return []
    return registeredAddresses.value.filter(reg => 
      connectedAddresses.value.includes(reg.address)
    )
  })

  const pendingAddresses = computed(() => 
    registeredAddresses.value.filter(a => !a.donationSent)
  )

  const completedAddresses = computed(() => 
    registeredAddresses.value.filter(a => a.donationSent)
  )

  // Actions
  function setConnectedWallet(walletName: string, addresses: string[]) {
    connectedWallet.value = walletName
    connectedAddresses.value = addresses
    error.value = null
  }

  function disconnectWallet() {
    connectedWallet.value = null
    connectedAddresses.value = []
  }

  function loadRegisteredAddresses(challenges: any) {
    const addresses: RegisteredAddress[] = []
    
    for (const [address, data] of Object.entries(challenges)) {
      const validatedCount = (data as any).challenge_queue?.filter(
        (c: any) => c.status === 'validated'
      ).length || 0

      addresses.push({
        address,
        validatedChallenges: validatedCount,
        donationSent: false
      })
    }

    registeredAddresses.value = addresses
    
    // Load saved progress from localStorage
    loadProgress()
  }

  function markDonationSent(address: string, signature?: string) {
    const addr = registeredAddresses.value.find(a => a.address === address)
    if (addr) {
      addr.donationSent = true
      addr.donationSignature = signature
      addr.lastUpdated = new Date().toISOString()
      saveProgress()
    }
  }

  function saveProgress() {
    const progress = registeredAddresses.value
      .filter(a => a.donationSent)
      .map(a => ({
        address: a.address,
        donationSent: a.donationSent,
        donationSignature: a.donationSignature,
        lastUpdated: a.lastUpdated
      }))
    
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress))
  }

  function loadProgress() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (!stored) return
      
      const progress = JSON.parse(stored)
      
      for (const saved of progress) {
        const addr = registeredAddresses.value.find(a => a.address === saved.address)
        if (addr) {
          addr.donationSent = saved.donationSent
          addr.donationSignature = saved.donationSignature
          addr.lastUpdated = saved.lastUpdated
        }
      }
    } catch (e) {
      console.error('Failed to load progress from localStorage:', e)
    }
  }

  function clearProgress() {
    localStorage.removeItem(STORAGE_KEY)
    registeredAddresses.value.forEach(a => {
      a.donationSent = false
      a.donationSignature = undefined
      a.lastUpdated = undefined
    })
  }

  function setError(message: string) {
    error.value = message
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    connectedWallet,
    connectedAddresses,
    registeredAddresses,
    donationAddress,
    isLoading,
    error,
    
    // Computed
    isConnected,
    matchedAddresses,
    pendingAddresses,
    completedAddresses,
    
    // Actions
    setConnectedWallet,
    disconnectWallet,
    loadRegisteredAddresses,
    markDonationSent,
    saveProgress,
    loadProgress,
    clearProgress,
    setError,
    clearError
  }
})
