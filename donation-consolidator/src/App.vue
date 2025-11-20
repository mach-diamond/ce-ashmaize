<script setup lang="ts">
import { onMounted, computed, ref } from 'vue'
import { useWalletStore } from './stores/walletStore'
import { useChallenges } from './composables/useChallenges'
import { 
  detectAvailableWallets, 
  connectWallet, 
  getWalletDisplayName,
  getCurrentWalletApi
} from './services/walletService'
import { submitDonation } from './services/donationService'

const walletStore = useWalletStore()
const { loadChallenges } = useChallenges()

const availableWallets = computed(() => detectAvailableWallets())

// Track curl commands for each address
const curlCommands = ref<Record<string, string>>({})

// Sort registered addresses - matched ones first
const sortedRegisteredAddresses = computed(() => {
  const matched = walletStore.registeredAddresses.filter(addr => 
    walletStore.connectedAddresses.includes(addr.address)
  )
  const unmatched = walletStore.registeredAddresses.filter(addr => 
    !walletStore.connectedAddresses.includes(addr.address)
  )
  return [...matched, ...unmatched]
})

// Load challenges on mount
onMounted(async () => {
  walletStore.isLoading = true
  const challenges = await loadChallenges()
  if (challenges) {
    walletStore.loadRegisteredAddresses(challenges)
  }
  walletStore.isLoading = false
})

// Connect to wallet
async function handleConnect(walletName: string) {
  try {
    walletStore.clearError()
    walletStore.isLoading = true
    
    const addresses = await connectWallet(walletName)
    walletStore.setConnectedWallet(walletName, addresses)
    
    console.log(`Connected! Wallet: ${walletName}, Found ${addresses.length} addresses`)
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to connect wallet'
    walletStore.setError(message)
    console.error('Connection error:', err)
  } finally {
    walletStore.isLoading = false
  }
}

// Shorten address for display
function shortenAddress(address: string, chars = 12): string {
  if (!address) return ''
  if (address.length <= chars * 2) return address
  return `${address.slice(0, chars)}...${address.slice(-chars)}`
}

// Copy to clipboard
function copyAddress(address: string) {
  navigator.clipboard.writeText(address)
}

// Handle donation submission
async function handleDonate(originalAddress: string) {
  if (!walletStore.donationAddress) {
    walletStore.setError('Please enter a donation address first')
    return
  }
  
  if (originalAddress === walletStore.donationAddress) {
    walletStore.setError('Cannot donate to the same address')
    return
  }
  
  const walletApi = getCurrentWalletApi()
  if (!walletApi) {
    walletStore.setError('No wallet connected')
    return
  }
  
  try {
    walletStore.clearError()
    walletStore.isLoading = true
    
    console.log(`Submitting donation from ${originalAddress} to ${walletStore.donationAddress}`)
    
    const result = await submitDonation(
      walletStore.donationAddress,
      originalAddress,
      walletApi
    )
    
    console.log('Donation result:', result)
    
    // Store the curl command for this address (in case user needs it)
    curlCommands.value[originalAddress] = result.curlCommand
    
    if (result.success && result.response) {
      // API submission successful!
      walletStore.markDonationSent(originalAddress, result.response)
      alert(`✓ Donation successful!\n\nConsolidated ${result.response.solutions_consolidated} solutions from\n${originalAddress.slice(0, 20)}...\n\nto\n${walletStore.donationAddress.slice(0, 20)}...`)
      // Clear the curl command since we don't need it
      delete curlCommands.value[originalAddress]
    } else {
      // API failed, show curl command
      walletStore.setError(result.error || 'Donation failed - see curl command below')
    }
    
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to submit donation'
    walletStore.setError(message)
    walletStore.markDonationError(originalAddress, message)
    console.error('Donation error:', err)
  } finally {
    walletStore.isLoading = false
  }
}

// Copy curl command to clipboard
function copyCurlCommand(address: string) {
  const cmd = curlCommands.value[address]
  if (cmd && navigator.clipboard) {
    navigator.clipboard.writeText(cmd)
    alert('Curl command copied to clipboard!')
  }
}

// Manual mark as consolidated
function markAsConsolidated(address: string) {
  const confirmed = confirm(`Mark ${address.slice(0, 20)}... as consolidated?`)
  if (confirmed) {
    walletStore.markDonationSent(address, {
      status: 'success',
      message: 'Manually marked as consolidated',
      donation_id: 'manual-' + Date.now(),
      original_address: address,
      destination_address: walletStore.donationAddress || '',
      timestamp: new Date().toISOString(),
      solutions_consolidated: 0
    })
    // Clear the curl command
    delete curlCommands.value[address]
  }
}

// Export progress
function handleExportProgress() {
  const json = walletStore.exportProgress()
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `midnight-consolidation-${Date.now()}.json`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

// Import progress
const fileInput = ref<HTMLInputElement | null>(null)

function handleImportClick() {
  fileInput.value?.click()
}

function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const jsonData = e.target?.result as string
      const result = walletStore.importProgress(jsonData)
      
      if (result.success) {
        alert(`✓ ${result.message}`)
      } else {
        alert(`✗ ${result.message}`)
      }
    } catch (err) {
      alert('Failed to read file')
    }
  }
  reader.readAsText(file)
  
  // Reset the input so the same file can be selected again
  input.value = ''
}

// Format NIGHT with commas
function formatNight(value: number): string {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="app">
    <header>
      <h1>🌙 Midnight Donation Consolidator</h1>
      <p>Connect wallet and consolidate mining rewards to a single address</p>
    </header>

    <!-- Error Display -->
    <div v-if="walletStore.error" class="error">
      <span>⚠️ {{ walletStore.error }}</span>
      <button @click="walletStore.clearError()">×</button>
    </div>

    <div class="container">
      <!-- Stats Summary -->
      <section class="card stats">
        <div class="stat-item">
          <div class="stat-value">{{ walletStore.registeredAddresses.length }}</div>
          <div class="stat-label">Total Addresses</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ walletStore.pendingAddresses.length }}</div>
          <div class="stat-label">Pending</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ walletStore.completedAddresses.length }}</div>
          <div class="stat-label">Completed</div>
        </div>
        <div class="stat-item">
          <div class="stat-value">{{ formatNight(walletStore.totalNightAllocation) }}</div>
          <div class="stat-label">Total $NIGHT (est.)</div>
        </div>
      </section>

      <!-- Wallet Connection -->
      <section class="card">
        <h2>Wallet Connection</h2>
        
        <div v-if="walletStore.isLoading" class="loading">
          Processing...
        </div>
        
        <div v-else-if="!walletStore.isConnected">
          <div v-if="availableWallets.length === 0" class="no-wallets">
            <p>❌ No Cardano wallets detected</p>
            <p class="hint">Install Nami, Eternl, Lace, or another Cardano wallet</p>
          </div>
          
          <div v-else class="wallet-list">
            <div 
              v-for="wallet in availableWallets" 
              :key="wallet"
              class="wallet-item"
            >
              <div class="wallet-name">
                <span class="icon">💳</span>
                <span>{{ getWalletDisplayName(wallet) }}</span>
              </div>
              <button 
                @click="handleConnect(wallet)"
                class="btn btn-primary"
                :disabled="walletStore.isLoading"
              >
                Connect
              </button>
            </div>
          </div>
        </div>

        <div v-else class="connected-info">
          <div class="connected-header">
            <div>
              <strong>{{ getWalletDisplayName(walletStore.connectedWallet || '') }}</strong>
              <span class="badge">✓ Connected</span>
            </div>
            <button @click="walletStore.disconnectWallet()" class="btn btn-secondary btn-sm">
              Disconnect
            </button>
          </div>

          <div class="addresses-section">
            <h3>Wallet Addresses ({{ walletStore.connectedAddresses.length }})</h3>
            <div class="address-list">
              <div 
                v-for="(addr, idx) in walletStore.connectedAddresses" 
                :key="addr"
                class="address-item"
                :class="{ 'is-registered': walletStore.registeredAddresses.some(r => r.address === addr) }"
              >
                <span class="address-index">{{ idx + 1 }}</span>
                <code class="address-text">{{ shortenAddress(addr, 16) }}</code>
                <span v-if="walletStore.registeredAddresses.some(r => r.address === addr)" class="registered-badge">
                  ✓ Registered
                </span>
                <button @click="copyAddress(addr)" class="btn-icon" title="Copy full address">
                  📋
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Donation Address Input -->
      <section class="card">
        <h2>Consolidation Destination</h2>
        <div class="donation-input">
          <label for="donation-address">Address to consolidate all rewards:</label>
          <input 
            id="donation-address"
            :value="walletStore.donationAddress"
            @input="walletStore.setDonationAddress(($event.target as HTMLInputElement).value)"
            type="text"
            placeholder="addr1..."
            class="input-address"
          />
          <div v-if="walletStore.donationAddress" class="address-info">
            <div class="address-preview">
              {{ shortenAddress(walletStore.donationAddress, 20) }}
            </div>
            <div class="destination-allocation">
              <strong>Total allocation for this address:</strong>
              <span class="night-value">{{ formatNight(walletStore.destinationAddressAllocation) }} $NIGHT (est.)</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Registered Addresses Table -->
      <section class="card">
        <div class="table-header">
          <h2>Registered Addresses</h2>
          <div class="header-actions">
            <button 
              @click="handleExportProgress"
              class="btn btn-secondary btn-sm"
              :disabled="walletStore.completedAddresses.length === 0"
              title="Export consolidation progress to file"
            >
              📥 Export
            </button>
            <button 
              @click="handleImportClick"
              class="btn btn-secondary btn-sm"
              title="Import consolidation progress from file"
            >
              📤 Import
            </button>
            <input 
              ref="fileInput"
              type="file" 
              accept=".json"
              @change="handleImportFile"
              style="display: none"
            />
            <button 
              v-if="walletStore.completedAddresses.length > 0"
              @click="walletStore.clearProgress()" 
              class="btn btn-secondary btn-sm"
            >
              Clear Progress
            </button>
          </div>
        </div>
        
        <div class="table-container">
          <table class="addresses-table">
            <thead>
              <tr>
                <th>Address</th>
                <th>Challenges</th>
                <th>$NIGHT (est.)</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr 
                v-for="addr in sortedRegisteredAddresses" 
                :key="addr.address"
                :class="{ 
                  'is-completed': addr.donationSent,
                  'is-matched': walletStore.connectedAddresses.includes(addr.address),
                  'is-consolidator': addr.isConsolidator
                }"
              >
                <td>
                  <div class="address-cell">
                    <code class="mono">{{ shortenAddress(addr.address, 16) }}</code>
                    <button @click="copyAddress(addr.address)" class="btn-icon" title="Copy">
                      📋
                    </button>
                    <span v-if="walletStore.connectedAddresses.includes(addr.address)" class="match-badge">
                      🔗 In Wallet
                    </span>
                  </div>
                </td>
                <td class="center">
                  <span class="challenge-count">{{ addr.validatedChallenges }}</span>
                </td>
                <td class="center">
                  <span class="night-amount">{{ formatNight(addr.nightAllocation) }}</span>
                </td>
                <td class="center">
                  <span v-if="addr.isConsolidator" class="status-badge status-consolidator">
                    🔵 Consolidator
                  </span>
                  <span v-else-if="addr.donationSent" class="status-badge status-done">
                    ✓ Done
                  </span>
                  <span v-else-if="addr.error" class="status-badge status-error">
                    ✗ Error
                  </span>
                  <span v-else class="status-badge status-pending">
                    Pending
                  </span>
                </td>
                <td class="center">
                  <!-- Consolidator Address - Show toggle button -->
                  <div v-if="addr.isConsolidator" class="consolidator-actions">
                    <div class="consolidator-info">
                      This is a consolidator address
                    </div>
                    <button 
                      @click="walletStore.toggleConsolidatorAddress(addr.address)"
                      class="btn btn-secondary btn-sm"
                      title="Remove consolidator status"
                    >
                      Remove Consolidator Status
                    </button>
                  </div>
                  
                  <!-- Only show action for connected wallet addresses that aren't consolidators -->
                  <div v-else-if="walletStore.connectedAddresses.includes(addr.address) && !addr.donationSent && addr.validatedChallenges > 0" class="donation-action">
                    <div class="allocation-info">
                      <div class="from-allocation">
                        <span class="label">From:</span>
                        <span class="value">{{ formatNight(addr.nightAllocation) }} $NIGHT</span>
                      </div>
                      <div class="arrow">→</div>
                      <div class="to-allocation">
                        <span class="label">To:</span>
                        <span class="value">{{ walletStore.donationAddress ? shortenAddress(walletStore.donationAddress, 8) : '(set address)' }}</span>
                      </div>
                    </div>
                    
                    <div style="display: flex; gap: 0.5rem; width: 100%;">
                      <button 
                        @click="handleDonate(addr.address)"
                        class="btn btn-success btn-sm"
                        style="flex: 1"
                        :disabled="!walletStore.donationAddress || !walletStore.isConnected || walletStore.isLoading"
                      >
                        <span v-if="walletStore.isLoading">...</span>
                        <span v-else>Donate</span>
                      </button>
                      
                      <button 
                        @click="markAsConsolidated(addr.address)"
                        class="btn btn-secondary btn-sm"
                        style="flex: 1"
                        title="Mark as consolidated after running curl manually"
                      >
                        ✓ Mark Done
                      </button>
                    </div>
                    
                    <!-- Button to mark as consolidator if it has donations sent to it -->
                    <button 
                      v-if="addr.validatedChallenges > 0"
                      @click="walletStore.toggleConsolidatorAddress(addr.address)"
                      class="btn btn-info btn-sm"
                      style="width: 100%; margin-top: 0.5rem;"
                      title="Mark this as a consolidator address (won't consolidate further)"
                    >
                      🔵 Mark as Consolidator
                    </button>
                    
                    <!-- Show curl command if available -->
                    <div v-if="curlCommands[addr.address]" class="curl-command-box">
                      <div class="curl-header">
                        <span>⚠️ Run this command in your terminal:</span>
                        <button @click="copyCurlCommand(addr.address)" class="btn-copy">📋 Copy</button>
                      </div>
                      <code class="curl-code">{{ curlCommands[addr.address] }}</code>
                    </div>
                  </div>
                  <div v-else-if="addr.donationSent" class="completed-info">
                    <div class="completed-badge">✓ Consolidated</div>
                    <div class="completed-time">
                      {{ addr.donationResponse?.timestamp ? new Date(addr.donationResponse.timestamp).toLocaleString() : '' }}
                    </div>
                    <div class="donation-id" v-if="addr.donationResponse?.donation_id">
                      ID: {{ addr.donationResponse.donation_id.slice(0, 8) }}...
                    </div>
                  </div>
                  <div v-else-if="addr.error" class="error-info">
                    <div class="error-badge">✗ Error</div>
                    <div class="error-message">{{ addr.error }}</div>
                  </div>
                  <div v-else-if="!walletStore.connectedAddresses.includes(addr.address)" class="not-in-wallet">
                    Not in connected wallet
                  </div>
                  <div v-else class="no-challenges">
                    No challenges
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  color: #e4e4e4;
  padding: 2rem 1rem;
  font-family: system-ui, -apple-system, sans-serif;
}

header {
  text-align: center;
  margin-bottom: 2rem;
}

header h1 {
  font-size: 2rem;
  margin: 0 0 0.5rem 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

header p {
  color: #a0a0a0;
  margin: 0;
}

.container {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.card {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 1.5rem;
  backdrop-filter: blur(10px);
}

.card h2 {
  margin: 0 0 1rem 0;
  font-size: 1.25rem;
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  padding: 1rem;
}

.stat-item {
  text-align: center;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
}

.stat-value {
  font-size: 2rem;
  font-weight: bold;
  color: #667eea;
  line-height: 1;
}

.stat-label {
  font-size: 0.85rem;
  color: #a0a0a0;
  margin-top: 0.5rem;
}

.error {
  max-width: 1400px;
  margin: 0 auto 1rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  padding: 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.error button {
  background: none;
  border: none;
  color: #ef4444;
  font-size: 1.5rem;
  cursor: pointer;
}

.loading {
  text-align: center;
  color: #a0a0a0;
  padding: 2rem;
}

.no-wallets {
  text-align: center;
  padding: 2rem;
}

.no-wallets .hint {
  color: #fbbf24;
  font-size: 0.9rem;
}

.wallet-list {
  display: grid;
  gap: 0.75rem;
}

.wallet-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
}

.wallet-name {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 1.1rem;
  font-weight: 500;
}

.icon {
  font-size: 1.5rem;
}

.connected-info {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.connected-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  border-radius: 8px;
}

.badge {
  color: #22c55e;
  font-size: 0.9rem;
  margin-left: 0.5rem;
}

.addresses-section h3 {
  font-size: 1rem;
  margin: 0 0 0.75rem 0;
  color: #a0a0a0;
}

.address-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.address-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
}

.address-item.is-registered {
  border-color: rgba(102, 126, 234, 0.5);
  background: rgba(102, 126, 234, 0.1);
}

.address-index {
  color: #a0a0a0;
  font-size: 0.85rem;
  min-width: 20px;
}

.address-text {
  flex: 1;
  font-family: 'Courier New', monospace;
  font-size: 0.9rem;
}

.registered-badge {
  color: #667eea;
  font-size: 0.85rem;
  font-weight: 500;
}

.donation-input {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.donation-input label {
  font-weight: 500;
  color: #a0a0a0;
}

.input-address {
  padding: 0.75rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: #e4e4e4;
  font-family: 'Courier New', monospace;
  font-size: 0.9rem;
}

.input-address:focus {
  outline: none;
  border-color: rgba(102, 126, 234, 0.5);
  background: rgba(255, 255, 255, 0.08);
}

.address-info {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.address-preview {
  color: #a0a0a0;
  font-size: 0.85rem;
  font-family: 'Courier New', monospace;
}

.destination-allocation {
  padding: 0.75rem;
  background: rgba(102, 126, 234, 0.1);
  border: 1px solid rgba(102, 126, 234, 0.3);
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.night-value {
  font-size: 1.25rem;
  font-weight: bold;
  color: #667eea;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.table-container {
  overflow-x: auto;
}

.addresses-table {
  width: 100%;
  border-collapse: collapse;
}

.addresses-table th {
  text-align: left;
  padding: 0.75rem;
  background: rgba(255, 255, 255, 0.05);
  border-bottom: 2px solid rgba(255, 255, 255, 0.1);
  font-weight: 500;
  color: #a0a0a0;
}

.addresses-table td {
  padding: 0.75rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.addresses-table tr.is-completed {
  opacity: 0.6;
}

.addresses-table tr.is-matched {
  background: rgba(102, 126, 234, 0.05);
}

.addresses-table tr.is-consolidator {
  background: rgba(59, 130, 246, 0.08);
  border-left: 3px solid #3b82f6;
}

.address-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.mono {
  font-family: 'Courier New', monospace;
  font-size: 0.85rem;
}

.match-badge {
  font-size: 0.75rem;
  color: #667eea;
  padding: 0.25rem 0.5rem;
  background: rgba(102, 126, 234, 0.2);
  border-radius: 4px;
}

.center {
  text-align: center;
}

.challenge-count {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  font-weight: 500;
}

.night-amount {
  font-family: 'Courier New', monospace;
  font-size: 0.9rem;
  color: #667eea;
}

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.85rem;
  font-weight: 500;
}

.status-consolidator {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.status-done {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.status-pending {
  background: rgba(251, 191, 36, 0.2);
  color: #fbbf24;
}

.status-error {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.completed-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  align-items: center;
}

.completed-badge {
  color: #22c55e;
  font-weight: 500;
  font-size: 0.85rem;
}

.completed-time {
  font-size: 0.7rem;
  color: #a0a0a0;
}

.donation-id {
  font-size: 0.7rem;
  color: #667eea;
  font-family: 'Courier New', monospace;
}

.error-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  align-items: center;
}

.error-badge {
  color: #ef4444;
  font-weight: 500;
  font-size: 0.85rem;
}

.error-message {
  font-size: 0.7rem;
  color: #ef4444;
  max-width: 250px;
  text-align: center;
}

.no-challenges {
  color: #a0a0a0;
  font-size: 0.85rem;
  font-style: italic;
}

.not-in-wallet {
  color: #a0a0a0;
  font-size: 0.85rem;
  font-style: italic;
}

.consolidator-actions {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  align-items: center;
  padding: 0.5rem;
}

.consolidator-info {
  color: #3b82f6;
  font-size: 0.85rem;
  font-weight: 500;
  text-align: center;
}

.donation-action {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  align-items: center;
  padding: 0.5rem;
}

.allocation-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 6px;
  font-size: 0.85rem;
}

.from-allocation,
.to-allocation {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.allocation-info .label {
  color: #a0a0a0;
  font-size: 0.7rem;
  text-transform: uppercase;
}

.allocation-info .value {
  color: #e4e4e4;
  font-weight: 500;
  font-family: 'Courier New', monospace;
  font-size: 0.8rem;
}

.arrow {
  color: #667eea;
  font-size: 1.2rem;
  font-weight: bold;
}

.btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-sm {
  padding: 0.35rem 0.75rem;
  font-size: 0.85rem;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.1);
  color: #e4e4e4;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.btn-secondary:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.15);
}

.btn-success {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.btn-success:hover:not(:disabled) {
  background: rgba(34, 197, 94, 0.3);
}

.btn-info {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.btn-info:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.3);
}

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.25rem;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.btn-icon:hover {
  opacity: 1;
}

.curl-command-box {
  width: 100%;
  margin-top: 1rem;
  padding: 1rem;
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.3);
  border-radius: 6px;
}

.curl-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
  font-size: 0.85rem;
  color: #fbbf24;
}

.btn-copy {
  background: rgba(251, 191, 36, 0.2);
  border: 1px solid rgba(251, 191, 36, 0.4);
  color: #fbbf24;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
}

.btn-copy:hover {
  background: rgba(251, 191, 36, 0.3);
}

.curl-code {
  display: block;
  width: 100%;
  max-width: 600px;
  padding: 0.75rem;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.7rem;
  color: #e4e4e4;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
