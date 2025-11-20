const API_BASE = 'https://sm.midnight.gd/api'

export interface StatisticsResponse {
  local: {
    crypto_receipts: number
    night_allocation: number
  }
  // May have other fields
}

// Official final $NIGHT values per solution for each campaign day
// These values are in the smallest unit (1 $NIGHT = 1,000,000 units)
const DAILY_NIGHT_VALUES = [
  6008676,   // Day 1
  3406761,   // Day 2
  3826220,   // Day 3
  5622964,   // Day 4
  3565984,   // Day 5
  2955878,   // Day 6
  2833044,   // Day 7
  2369902,   // Day 8
  2254948,   // Day 9
  2319671,   // Day 10
  2740022,   // Day 11
  2592181,   // Day 12
  2289733,   // Day 13
  2881997,   // Day 14
  3498531,   // Day 15
  3119269,   // Day 16
  2726926,   // Day 17
  2269176,   // Day 18
  2197111,   // Day 19
  3657916,   // Day 20
  15695416   // Day 21
]

// Convert to actual $NIGHT (divide by 1,000,000)
const DAILY_NIGHT_VALUES_CONVERTED = DAILY_NIGHT_VALUES.map(v => v / 1000000)

// Calculate average for days we don't have data for
const AVERAGE_NIGHT_VALUE = DAILY_NIGHT_VALUES_CONVERTED.reduce((a, b) => a + b, 0) / DAILY_NIGHT_VALUES_CONVERTED.length

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
    const nightPerSolution = dayIndex < DAILY_NIGHT_VALUES_CONVERTED.length 
      ? DAILY_NIGHT_VALUES_CONVERTED[dayIndex] 
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
