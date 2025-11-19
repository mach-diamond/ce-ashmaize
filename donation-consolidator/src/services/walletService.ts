// Common Cardano wallet names available in browser
export const SUPPORTED_WALLETS = [
  'nami',
  'eternl',
  'flint',
  'lace',
  'typhon',
  'gerowallet',
  'nufi',
  'vespr',
  'begin',
  'yoroi'
] as const

export type WalletName = typeof SUPPORTED_WALLETS[number]

// Store the wallet API for signing
let currentWalletApi: any = null

export function getCurrentWalletApi() {
  return currentWalletApi
}

// Decode hex address to bech32 format
function hexToAddress(hexAddress: string): string {
  try {
    const cleanHex = hexAddress.startsWith('0x') ? hexAddress.slice(2) : hexAddress
    const bytes = new Uint8Array(cleanHex.match(/.{1,2}/g)!.map(byte => parseInt(byte, 16)))
    
    const header = bytes[0]
    const isTestnet = (header & 0x0F) === 0
    const prefix = isTestnet ? 'addr_test' : 'addr'
    
    const charset = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
    
    const data: number[] = []
    let acc = 0
    let bits = 0
    
    for (const byte of bytes) {
      acc = (acc << 8) | byte
      bits += 8
      while (bits >= 5) {
        bits -= 5
        data.push((acc >> bits) & 31)
      }
    }
    
    if (bits > 0) {
      data.push((acc << (5 - bits)) & 31)
    }
    
    const checksum = createChecksum(prefix, data)
    const combined = data.concat(checksum)
    
    return prefix + '1' + combined.map(d => charset[d]).join('')
  } catch (error) {
    console.error('Error decoding address:', error)
    throw new Error('Failed to decode address from hex')
  }
}

function createChecksum(hrp: string, data: number[]): number[] {
  const values = hrpExpand(hrp).concat(data).concat([0, 0, 0, 0, 0, 0])
  const polymod = bech32Polymod(values) ^ 1
  const checksum: number[] = []
  for (let i = 0; i < 6; i++) {
    checksum.push((polymod >> (5 * (5 - i))) & 31)
  }
  return checksum
}

function hrpExpand(hrp: string): number[] {
  const result: number[] = []
  for (let i = 0; i < hrp.length; i++) {
    result.push(hrp.charCodeAt(i) >> 5)
  }
  result.push(0)
  for (let i = 0; i < hrp.length; i++) {
    result.push(hrp.charCodeAt(i) & 31)
  }
  return result
}

function bech32Polymod(values: number[]): number {
  const generator = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
  let chk = 1
  for (const value of values) {
    const top = chk >> 25
    chk = ((chk & 0x1ffffff) << 5) ^ value
    for (let i = 0; i < 5; i++) {
      if ((top >> i) & 1) {
        chk ^= generator[i]
      }
    }
  }
  return chk
}

// Check which wallets are available in the browser
export function detectAvailableWallets(): string[] {
  const available: string[] = []
  
  if (typeof window === 'undefined') return available
  
  // @ts-ignore - cardano object is injected by wallet extensions
  const cardano = window.cardano
  
  if (!cardano) {
    console.log('No window.cardano object found')
    return available
  }
  
  console.log('Cardano object detected:', Object.keys(cardano))
  
  SUPPORTED_WALLETS.forEach(walletName => {
    if (cardano[walletName]) {
      console.log(`Found wallet: ${walletName}`)
      available.push(walletName)
    }
  })
  
  return available
}

// Get ALL addresses from a wallet
export async function connectWallet(walletName: string): Promise<string[]> {
  // @ts-ignore
  const cardano = window.cardano
  
  if (!cardano || !cardano[walletName]) {
    throw new Error(`${walletName} wallet not found`)
  }
  
  try {
    console.log(`Attempting to connect to ${walletName}...`)
    
    // Enable the wallet (this will prompt user for permission)
    const api = await cardano[walletName].enable()
    console.log(`${walletName} enabled, API:`, api)
    
    // Store the API for later use in signing
    currentWalletApi = api
    
    const addresses: string[] = []
    const addressSet = new Set<string>()
    
    // Helper to add address to set (avoiding duplicates)
    const addAddress = (addr: string) => {
      if (addr && !addressSet.has(addr)) {
        addressSet.add(addr)
        addresses.push(addr)
      }
    }
    
    // Method 1: Get change address
    try {
      const changeAddressHex = await api.getChangeAddress()
      console.log('getChangeAddress returned:', changeAddressHex)
      
      if (changeAddressHex.startsWith('addr1') || changeAddressHex.startsWith('addr_test')) {
        addAddress(changeAddressHex)
      } else {
        addAddress(hexToAddress(changeAddressHex))
      }
    } catch (e) {
      console.log('getChangeAddress failed:', e)
    }
    
    // Method 2: Get ALL used addresses
    try {
      const usedAddresses = await api.getUsedAddresses()
      console.log('getUsedAddresses returned:', usedAddresses)
      
      if (usedAddresses && usedAddresses.length > 0) {
        for (const addr of usedAddresses) {
          if (addr.startsWith('addr1') || addr.startsWith('addr_test')) {
            addAddress(addr)
          } else {
            try {
              addAddress(hexToAddress(addr))
            } catch (e) {
              console.log('Failed to decode address:', addr, e)
            }
          }
        }
      }
    } catch (e) {
      console.log('getUsedAddresses failed:', e)
    }
    
    // Method 3: Get unused addresses
    try {
      const unusedAddresses = await api.getUnusedAddresses()
      console.log('getUnusedAddresses returned:', unusedAddresses)
      
      if (unusedAddresses && unusedAddresses.length > 0) {
        for (const addr of unusedAddresses) {
          if (addr.startsWith('addr1') || addr.startsWith('addr_test')) {
            addAddress(addr)
          } else {
            try {
              addAddress(hexToAddress(addr))
            } catch (e) {
              console.log('Failed to decode address:', addr, e)
            }
          }
        }
      }
    } catch (e) {
      console.log('getUnusedAddresses failed:', e)
    }
    
    if (addresses.length === 0) {
      throw new Error('Could not retrieve any addresses from wallet')
    }
    
    console.log(`Successfully connected to ${walletName}, found ${addresses.length} addresses:`, addresses)
    return addresses
    
  } catch (error) {
    console.error(`Error connecting to ${walletName}:`, error)
    throw new Error(`Failed to connect to ${walletName}: ${error}`)
  }
}

// Get wallet display name (capitalize first letter)
export function getWalletDisplayName(walletName: string): string {
  return walletName.charAt(0).toUpperCase() + walletName.slice(1)
}
