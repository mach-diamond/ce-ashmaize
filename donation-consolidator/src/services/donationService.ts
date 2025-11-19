const API_BASE = 'https://scavenger.prod.gd.midnighttge.io'

export interface DonationResponse {
  status: string
  message: string
  donation_id: string
  original_address: string
  destination_address: string
  timestamp: string
  solutions_consolidated: number
}

// Sign and submit donation request
export async function submitDonation(
  destinationAddress: string,
  originalAddress: string,
  walletApi: any
): Promise<DonationResponse> {
  
  // Construct the message to sign
  const message = `Assign accumulated Scavenger rights to: ${destinationAddress}`
  
  console.log('Signing message:', message)
  
  // Sign the message using CIP-30
  const signature = await walletApi.signData(originalAddress, message)
  
  console.log('Signature:', signature)
  
  // The signature should be in the format returned by the wallet
  const signatureHex = signature.signature
  
  // Construct the API URL
  const url = `${API_BASE}/donate_to/${destinationAddress}/${originalAddress}/${signatureHex}`
  
  console.log('Submitting to:', url)
  
  // Submit to API
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: '{}'
  })
  
  if (!response.ok) {
    const errorData = await response.json()
    throw new Error(errorData.message || `API request failed: ${response.status}`)
  }
  
  const data = await response.json()
  return data as DonationResponse
}
