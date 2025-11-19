<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useWalletStore } from './stores/walletStore'
import { useChallenges } from './composables/useChallenges'
import { detectAvailableWallets, connectWallet, getWalletDisplayName } from './services/walletService'

const walletStore = useWalletStore()
const { loadChallenges } = useChallenges()

const availableWallets = computed(() => detectAvailableWallets())

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
</script>

<template>
  <div class="app">
    <header>
      <h1>🌙 Midnight Donation Consolidator</h1>
      <p>Connect wallet and process donation requests for registered addresses</p>
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
          <div class="stat-value">{{ walletStore.matchedAddresses.length }}</div>
          <div class="stat-label">In Connected Wallet</div>
        </div>
      </section>

      <!-- Wallet Connection -->
      <section class="card">
        <h2>Wallet Connection</h2>
        
        <div v-if="walletStore.isLoading" class="loading">
          Loading...
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
          <label for="donation-address">Address to send all donations:</label>
          <input 
            id="donation-address"
            v-model="walletStore.donationAddress"
            type="text"
            placeholder="addr1..."
            class="input-address"
          />
          <div v-if="walletStore.donationAddress" class="address-preview">
            {{ shortenAddress(walletStore.donationAddress, 20) }}
          </div>
        </div>
      </section>

      <!-- Registered Addresses Table -->
      <section class="card">
        <div class="table-header">
          <h2>Registered Addresses</h2>
          <button 
            v-if="walletStore.completedAddresses.length > 0"
            @click="walletStore.clearProgress()" 
            class="btn btn-secondary btn-sm"
          >
            Clear Progress
          </button>
        </div>
        
        <div class="table-container">
          <table class="addresses-table">
            <thead>
              <tr>
                <th>Address</th>
                <th>Validated</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr 
                v-for="addr in walletStore.registeredAddresses" 
                :key="addr.address"
                :class="{ 
                  'is-completed': addr.donationSent,
                  'is-matched': walletStore.connectedAddresses.includes(addr.address)
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
                  <span v-if="addr.donationSent" class="status-badge status-done">
                    ✓ Done
                  </span>
                  <span v-else class="status-badge status-pending">
                    Pending
                  </span>
                </td>
                <td class="center">
                  <button 
                    v-if="!addr.donationSent"
                    @click="walletStore.markDonationSent(addr.address)"
                    class="btn btn-success btn-sm"
                  >
                    Mark Done
                  </button>
                  <span v-else class="completed-time">
                    {{ addr.lastUpdated ? new Date(addr.lastUpdated).toLocaleString() : '' }}
                  </span>
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
  font-size: 2.5rem;
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

.address-preview {
  color: #a0a0a0;
  font-size: 0.85rem;
  font-family: 'Courier New', monospace;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
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

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 12px;
  font-size: 0.85rem;
  font-weight: 500;
}

.status-done {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
}

.status-pending {
  background: rgba(251, 191, 36, 0.2);
  color: #fbbf24;
}

.completed-time {
  font-size: 0.75rem;
  color: #a0a0a0;
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

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-secondary {
  background: rgba(255, 255, 255, 0.1);
  color: #e4e4e4;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.15);
}

.btn-success {
  background: rgba(34, 197, 94, 0.2);
  color: #22c55e;
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.btn-success:hover {
  background: rgba(34, 197, 94, 0.3);
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
</style>
