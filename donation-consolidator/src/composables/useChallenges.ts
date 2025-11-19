import { ref } from 'vue'

export function useChallenges() {
  const challenges = ref<any>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function loadChallenges() {
    isLoading.value = true
    error.value = null

    try {
      // Path to your challenges.json file
      const response = await fetch('/challenges.json')
      
      if (!response.ok) {
        throw new Error('Failed to load challenges.json')
      }
      
      const data = await response.json()
      challenges.value = data
      return data
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error loading challenges'
      console.error('Error loading challenges:', err)
      return null
    } finally {
      isLoading.value = false
    }
  }

  return {
    challenges,
    isLoading,
    error,
    loadChallenges
  }
}
