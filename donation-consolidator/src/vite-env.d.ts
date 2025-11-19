/// <reference types="vite/client" />

interface CardanoWalletAPI {
  enable(): Promise<any>
  isEnabled(): Promise<boolean>
  apiVersion: string
  name: string
  icon: string
}

interface Window {
  cardano?: {
    [key: string]: CardanoWalletAPI
  }
}
