import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { estimateNightAllocation } from '../services/statisticsService'

export interface DonationResponse {
  status: string
  message: string
  donation_id: string
  original_address: string
  destination_address: string
  timestamp: string
  solutions_consolidated: number
}

export interface RegisteredAddress {
  address: string
  validatedChallenges: number
  starAllocation: number
  nightAllocation: number
  donationSent: boolean
  donationResponse?: DonationResponse
  error?: string
}

const STORAGE_KEY = 'midnight-donation-tracker'
const DONATION_ADDRESS_KEY = 'midnight-donation-address'
const WORK_TO_STAR_RATE_KEY = 'midnight-work-to-star-rate'

export const useWalletStore = defineStore('wallet', () => {
  // State
  const connectedWallet = ref<string | null>(null)
  const connectedAddresses = ref<string[]>([])
  const registeredAddresses = ref<RegisteredAddress[]>([])
  const donationAddress = ref<string>('')
  const workToStarRate = ref<number[]>([])
  const isLoading = ref(false)
  const isFetchingStatistics = ref(false)
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
    registeredAddresses.value.filter(a => !a.donationSent && a.starAllocation > 0)
  )

  const completedAddresses = computed(() => 
    registeredAddresses.value.filter(a => a.donationSent)
  )

  const totalNightAllocation = computed(() => {
    return registeredAddresses.value.reduce((sum, addr) => sum + addr.nightAllocation, 0)
  })

  const destinationAddressAllocation = computed(() => {
    if (!donationAddress.value) return 0
    
    // Find the destination address in registered addresses
    const destAddr = registeredAddresses.value.find(a => a.address === donationAddress.value)
    const ownAllocation = destAddr ? destAddr.nightAllocation : 0
    
    // Sum up all addresses that have donated to this destination
    const donatedAllocation = registeredAddresses.value
      .filter(a => a.donationSent && a.address !== donationAddress.value)
      .reduce((sum, addr) => sum + addr.nightAllocation, 0)
    
    return ownAllocation + donatedAllocation
  })

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

  function calculateStarAllocation(challengeQueue: any[]): number {
    if (!challengeQueue || challengeQueue.length === 0 || workToStarRate.value.length === 0) {
      // Fallback calculation if work_to_star_rate is not available
      return challengeQueue?.filter((c: any) => c.status === 'validated').length * 10000000 || 0
    }

    let totalStar = 0
    const dailyCounts: { [day: number]: number } = {}

    // Count validated challenges per day
    for (const challenge of challengeQueue) {
      if (challenge.status === 'validated') {
        const day = challenge.campaignDay
        dailyCounts[day] = (dailyCounts[day] || 0) + 1
      }
    }

    // Calculate STAR based on work_to_star_rate
    for (const [day, count] of Object.entries(dailyCounts)) {
      const dayIndex = parseInt(day) - 1 // Day 1 = index 0
      if (dayIndex >= 0 && dayIndex < workToStarRate.value.length) {
        totalStar += count * workToStarRate.value[dayIndex]
      }
    }

    return totalStar
  }

  function loadRegisteredAddresses(challenges: any) {
    const addresses: RegisteredAddress[] = []
    
    for (const [address, data] of Object.entries(challenges)) {
      const challengeQueue = (data as any).challenge_queue || []
      const validatedCount = challengeQueue.filter(
        (c: any) => c.status === 'validated'
      ).length

      // Use estimation for NIGHT allocation
      const estimatedNight = estimateNightAllocation(challengeQueue)

      addresses.push({
        address,
        validatedChallenges: validatedCount,
        starAllocation: 0, // Keep for compatibility, but we're using NIGHT now
        nightAllocation: estimatedNight,
        donationSent: false
      })
    }

    registeredAddresses.value = addresses
    
    // Load saved progress from localStorage
    loadProgress()
    
    // Load saved donation address
    loadDonationAddress()
    
    // Load work_to_star_rate if available
    loadWorkToStarRate()
  }

  function setDonationAddress(address: string) {
    donationAddress.value = address
    saveDonationAddress()
  }

  function saveDonationAddress() {
    if (donationAddress.value) {
      localStorage.setItem(DONATION_ADDRESS_KEY, donationAddress.value)
    }
  }

  function loadDonationAddress() {
    const saved = localStorage.getItem(DONATION_ADDRESS_KEY)
    if (saved) {
      donationAddress.value = saved
    }
  }

  function setWorkToStarRate(rates: number[]) {
    workToStarRate.value = rates
    localStorage.setItem(WORK_TO_STAR_RATE_KEY, JSON.stringify(rates))
    
    // Recalculate all allocations with new rates
    for (const addr of registeredAddresses.value) {
      // We need the original challenge queue - this would require reloading
      // For now, just update if we have the data
      addr.nightAllocation = addr.starAllocation / 1000000
    }
  }

  function loadWorkToStarRate() {
    const saved = localStorage.getItem(WORK_TO_STAR_RATE_KEY)
    if (saved) {
      try {
        workToStarRate.value = JSON.parse(saved)
      } catch (e) {
        console.error('Failed to load work_to_star_rate from localStorage:', e)
      }
    }
  }

  function updateAddressStatistics(address: string, starAllocation: number) {
    const addr = registeredAddresses.value.find(a => a.address === address)
    if (addr) {
      addr.starAllocation = starAllocation
      addr.nightAllocation = starAllocation / 1000000
    }
  }

  function markDonationSent(address: string, response: DonationResponse) {
    const addr = registeredAddresses.value.find(a => a.address === address)
    if (addr) {
      addr.donationSent = true
      addr.donationResponse = response
      addr.error = undefined
      saveProgress()
    }
  }

  function markDonationError(address: string, errorMsg: string) {
    const addr = registeredAddresses.value.find(a => a.address === address)
    if (addr) {
      addr.error = errorMsg
    }
  }

  function saveProgress() {
    const progress = registeredAddresses.value
      .filter(a => a.donationSent)
      .map(a => ({
        address: a.address,
        donationSent: a.donationSent,
        donationResponse: a.donationResponse
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
          addr.donationResponse = saved.donationResponse
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
      a.donationResponse = undefined
      a.error = undefined
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
    workToStarRate,
    isLoading,
    isFetchingStatistics,
    error,
    
    // Computed
    isConnected,
    matchedAddresses,
    pendingAddresses,
    completedAddresses,
    totalNightAllocation,
    destinationAddressAllocation,
    
    // Actions
    setConnectedWallet,
    disconnectWallet,
    loadRegisteredAddresses,
    setDonationAddress,
    setWorkToStarRate,
    updateAddressStatistics,
    markDonationSent,
    markDonationError,
    saveProgress,
    loadProgress,
    clearProgress,
    setError,
    clearError
  }
})
