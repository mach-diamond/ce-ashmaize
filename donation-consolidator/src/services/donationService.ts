// Use direct API for donations (signature URLs are too long for proxy)
// Use Vite proxy for other endpoints in development
const API_BASE = 'https://scavenger.prod.gd.midnighttge.io'

export interface DonationResponse {  status: string
  message: string
  donation_id: string
  original_address: string
  destination_address: string
  timestamp: string
  solutions_consolidated: number
}

export interface DonationResult {
  success: boolean
  curlCommand: string
  response?: DonationResponse
  error?: string
}

// Check if an address has already been consolidated
export async function checkDonationStatus(address: string): Promise<DonationResponse | null> {
  try {
    // The API should have an endpoint to check donation status
    // Based on the docs, we can try to get the address info
    // For now, we'll return null and rely on localStorage
    // TODO: Find the correct API endpoint to check donation status
    return null
  } catch (err) {
    console.error('Error checking donation status:', err)
    return null
  }
}

// Sign and submit donation request
export async function submitDonation(
  destinationAddress: string,
  originalAddress: string,
  walletApi: any
): Promise<DonationResult> {
  
  // Construct the message to sign
  const message = `Assign accumulated Scavenger rights to: ${destinationAddress}`
  
  console.log('Signing message:', message)
  console.log('Message length:', message.length)
  
  // Convert message to hex (CIP-30 expects hex-encoded messages)
  const messageHex = Array.from(message)
    .map(c => c.charCodeAt(0).toString(16).padStart(2, '0'))
    .join('')
  
  console.log('Message hex:', messageHex)
  
  // Sign the message using CIP-30 with hex-encoded message
  const signature = await walletApi.signData(originalAddress, messageHex)
  
  console.log('Signature object:', signature)
  console.log('Signature hex length:', signature.signature.length)
  
  // The signature should be in the format returned by the wallet
  const signatureHex = signature.signature
  
  // Construct the API URL
  const url = `${API_BASE}/donate_to/${destinationAddress}/${originalAddress}/${signatureHex}`
  
  console.log('Submitting to:', url)
  
  // Print curl command for debugging
  const fullUrl = `https://scavenger.prod.gd.midnighttge.io/donate_to/${destinationAddress}/${originalAddress}/${signatureHex}`
  const curlCommand = `curl -L -X POST "${fullUrl}" -d "{}"`
  
  console.log('\n=== COPY THIS CURL COMMAND AND RUN IT IN YOUR TERMINAL ===')
  console.log(curlCommand)
  console.log('\n=== Or run this in browser console to copy to clipboard: ===')
  console.log(`copy(\`${curlCommand}\`)`)
  console.log('====================================\n')
  
  // Try to copy to clipboard automatically
  try {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(curlCommand)
      console.log('✓ Curl command copied to clipboard!')
    }
  } catch (e) {
    console.log('Could not auto-copy to clipboard')
  }
  
  // Submit to API
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: '{}'
  }).catch(err => {
    // CORS error - return curl command
    if (err.message.includes('Failed to fetch') || err.message.includes('CORS')) {
      return {
        success: false,
        curlCommand,
        error: 'CORS blocked - use the curl command below'
      }
    }
    throw err
  })
  
  if (!response || !response.ok) {
    let errorMessage = response ? `API request failed: ${response.status}` : 'No response'
    try {
      if (response) {
        const errorData = await response.json()
        errorMessage = errorData.message || errorMessage
        console.error('API Error:', errorData)
      }
    } catch (e) {
      // Ignore
    }
    return {
      success: false,
      curlCommand,
      error: errorMessage
    }
  }
  
  const data = await response.json()
  return {
    success: true,
    curlCommand,
    response: data as DonationResponse
  }
}
