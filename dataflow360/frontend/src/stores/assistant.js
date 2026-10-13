import { defineStore } from 'pinia'
import { api } from '../lib/api'

export const useAssistant = defineStore('assistant', {
  state: () => ({
    messages: [],        // historique de la conversation
    busy: false,         // true pendant qu'une réponse est en cours
    pendingQuestion: '', // question en cours (pour réafficher)
  }),
  actions: {
    async ask(text) {
      const content = (text || '').trim()
      if (!content || this.busy) return

      // Ajoute la question de l'utilisateur
      this.messages.push({ role: 'user', text: content })
      this.busy = true
      this.pendingQuestion = content

      try {
        const res = await api.post('/api/v1/assistant/query', { question: content })
        this.messages.push({
          role: 'bot',
          text: res.answer,
          sources: res.sources_count,
        })
      } catch (e) {
        this.messages.push({
          role: 'bot',
          text: e.message,
          error: true,
        })
      } finally {
        this.busy = false
        this.pendingQuestion = ''
      }
    },
    clear() {
      this.messages = []
    },
  },
})
