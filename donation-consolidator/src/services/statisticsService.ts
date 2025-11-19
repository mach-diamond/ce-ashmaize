const API_BASE = 'https://sm.midnight.gd/api'

export interface StatisticsResponse {
  local: {
    crypto_receipts: number
    night_allocation: number
  }
  // May have other fields
}

// Historical daily $NIGHT values for estimation
const DAILY_NIGHT_VALUES = [
  5.95, 3.41, 3.83, 5.62, 3.57, 2.96, 2.83, 2.37, 
  2.25, 2.32, 2.74, 2.59, 2.29, 2.88, 3.5, 3.12, 2.73, 2.27
]

// Calculate average for days we don't have data for
const AVERAGE_NIGHT_VALUE = DAILY_NIGHT_VALUES.reduce((a, b) => a + b, 0) / DAILY_NIGHT_VALUES.length

// Estimate NIGHT allocation based on challenge data
export function estimateNightAllocation(challengeQueue: any[]): number {
  if (!challengeQueue || challengeQueue.length === 0) {
    return 0
  }

  const dailyCounts: { [day: number]: number } = {}

  // Count validated challenges per day
  for (const challenge of challengeQueue) {
    if (challenge.status === 'validated') {
      const day = challenge.campaignDay
      dailyCounts[day] = (dailyCounts[day] || 0) + 1
    }
  }

  // Calculate total NIGHT based on daily values
  let totalNight = 0
  for (const [day, count] of Object.entries(dailyCounts)) {
    const dayIndex = parseInt(day) - 1 // Day 1 = index 0
    const nightPerSolution = dayIndex < DAILY_NIGHT_VALUES.length 
      ? DAILY_NIGHT_VALUES[dayIndex] 
      : AVERAGE_NIGHT_VALUE
    
    totalNight += count * nightPerSolution
  }

  return totalNight
}

// Fetch statistics for an address
export async function fetchAddressStatistics(address: string): Promise<StatisticsResponse> {
  const url = `${API_BASE}/statistics/${address}`
  
  console.log('Fetching statistics for:', address)
  
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json'
    }
  })
  
  if (!response.ok) {
    throw new Error(`Failed to fetch statistics: ${response.status}`)
  }
  
  const data = await response.json()
  console.log('Statistics for', address, ':', data)
  
  return data as StatisticsResponse
}

// Batch fetch statistics for multiple addresses
export async function fetchBatchStatistics(
  addresses: string[],
  onProgress?: (current: number, total: number) => void
): Promise<Map<string, StatisticsResponse>> {
  const results = new Map<string, StatisticsResponse>()
  
  for (let i = 0; i < addresses.length; i++) {
    const address = addresses[i]
    
    try {
      const stats = await fetchAddressStatistics(address)
      results.set(address, stats)
      
      if (onProgress) {
        onProgress(i + 1, addresses.length)
      }
      
      // Small delay to avoid rate limiting
      if (i < addresses.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 100))
      }
    } catch (error) {
      console.error(`Failed to fetch statistics for ${address}:`, error)
      // Continue with other addresses even if one fails
    }
  }
  
  return results
}
