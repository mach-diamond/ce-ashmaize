# 🌙 Midnight Donation Consolidator

A Vue.js application for consolidating Midnight Network mining rewards from multiple addresses into a single destination address using Cardano browser wallets.

## Features

- **Wallet Integration**: Connect Nami, Eternl, Lace, or other Cardano browser wallets
- **Multi-Address Support**: View all registered mining addresses and their estimated rewards
- **Estimated Rewards**: Shows estimated $NIGHT allocation based on validated challenges
- **Progress Tracking**: Tracks donation status with localStorage persistence
- **Browser-Based Signing**: Sign donation requests directly with your Cardano wallet

## Prerequisites

### Install Bun

This project uses [Bun](https://bun.sh) as the JavaScript runtime and package manager.

**macOS/Linux:**
```bash
curl -fsSL https://bun.sh/install | bash
```

**Windows:**
```bash
powershell -c "irm bun.sh/install.ps1 | iex"
```

After installation, restart your terminal and verify:
```bash
bun --version
```

### Cardano Browser Wallet

Install one of the following Cardano wallet browser extensions:
- [Nami Wallet](https://namiwallet.io/)
- [Eternl Wallet](https://eternl.io/)
- [Lace Wallet](https://www.lace.io/)

## Setup

### 1. Prepare Challenge Data

Copy your mining challenge history into the project:

```bash
# From the project root directory
cp ../cli-hunt/python-orchestrator/challenges.json ./public/challenges.json
```

**Note**: The `challenges.json` file contains your mining history and must be present in the `public` directory for the app to load your registered addresses.

### 2. Install Dependencies

```bash
bun install
```

## Running the Application

### Development Server

Start the development server with hot-reload:

```bash
bun run dev
```

The application will be available at `http://localhost:5173` (or the next available port).

### Production Build

Build for production:

```bash
bun run build
```

Preview the production build:

```bash
bun run preview
```

## Usage

### 1. Connect Your Wallet

1. Open the application in your browser
2. Click "Connect" next to your preferred Cardano wallet
3. Approve the connection request in your wallet extension
4. The app will load all addresses from your wallet

### 2. Review Your Mining Addresses

- The app will display all registered mining addresses from `challenges.json`
- Each address shows:
  - Number of validated challenges
  - Estimated $NIGHT rewards (based on historical daily values)
  - Current donation status (Pending/Done/Error)
- Addresses that match your connected wallet are highlighted with "🔗 In Wallet"

### 3. Set Consolidation Destination

1. Enter the Cardano address where you want to consolidate all rewards
2. The app will show the total estimated allocation for that address
3. This includes both the destination address's own rewards plus any already consolidated rewards

### 4. Send Donations

1. For each address you want to consolidate, click "Send Donation"
2. Your wallet will prompt you to sign the donation request
3. After signing, the donation is submitted to the Midnight Network API
4. Completed donations are marked and progress is saved locally

## Project Structure

```
donation-consolidator/
├── public/
│   ├── challenges.json      # Your mining history (copy from cli-hunt)
│   └── favicon.ico
├── src/
│   ├── App.vue              # Main application component
│   ├── main.ts              # Application entry point
│   ├── composables/
│   │   └── useChallenges.ts # Challenge data loading
│   ├── services/
│   │   ├── donationService.ts      # Donation API calls
│   │   ├── statisticsService.ts    # Reward estimation logic
│   │   └── walletService.ts        # Cardano wallet integration
│   └── stores/
│       └── walletStore.ts   # Pinia store for state management
├── package.json
└── README.md
```

## How Rewards Are Estimated

The app estimates $NIGHT rewards based on:

1. **Historical Daily Values**: Uses archived daily $NIGHT-per-solution values for days 1-18
2. **Average Fallback**: For days beyond day 18, uses the average of known values (~3.18 $NIGHT)
3. **Per-Address Calculation**: Counts validated challenges per day and multiplies by the corresponding daily value

**Note**: These are estimates based on historical data. Actual rewards may vary when the Midnight Network API provides official statistics.

## Troubleshooting

### Wallet Not Detected

- Ensure your Cardano wallet extension is installed and enabled
- Refresh the page after installing the wallet extension
- Try disabling and re-enabling the extension

### challenges.json Not Found

```
Error loading challenges.json
```

**Solution**: Copy the file from your mining directory:
```bash
cp ../cli-hunt/python-orchestrator/challenges.json ./public/challenges.json
```

### Connection Refused

If the wallet connection fails:
1. Check that you're not in private/incognito mode
2. Ensure the wallet is unlocked
3. Try disconnecting and reconnecting
4. Check browser console for detailed error messages

### Invalid Donation Address

- Ensure the destination address is a valid Cardano address (starts with `addr1`)
- You cannot donate from an address to itself

## Development

### Available Scripts

- `bun run dev` - Start development server
- `bun run build` - Build for production
- `bun run preview` - Preview production build
- `bun run lint` - Lint code with ESLint

### Tech Stack

- **Vue 3** - Progressive JavaScript framework
- **TypeScript** - Type-safe JavaScript
- **Pinia** - State management
- **Vite** - Build tool and dev server
- **Bun** - JavaScript runtime and package manager

## Security Notes

- Your wallet's private keys never leave your browser
- The app only requests signing permissions for donation transactions
- Progress is saved locally in your browser's localStorage
- No sensitive data is transmitted except signed donation requests

## License

This project is part of the Midnight Network mining ecosystem.
