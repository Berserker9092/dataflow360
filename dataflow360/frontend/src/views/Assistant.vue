<script setup>
import { ref, nextTick, watch } from 'vue'
import { Send, Sparkles } from 'lucide-vue-next'
import { useAssistant } from '../stores/assistant'

const assistant = useAssistant()
const question = ref('')
const log = ref(null)

const SUGGESTIONS = [
  'Quels sont les problèmes de livraison les plus cités ?',
  'Les clients sont-ils satisfaits de la qualité des produits ?',
  'Quels sujets reviennent le plus dans les tickets support ?',
]

const scroll = () => nextTick(() => log.value && (log.value.scrollTop = log.value.scrollHeight))

async function ask(text) {
  const content = (text ?? question.value).trim()
  if (!content || assistant.busy) return
  question.value = ''
  await assistant.ask(content)
  scroll()
}

// Auto-scroll quand de nouveaux messages arrivent
watch(() => assistant.messages.length, scroll)
watch(() => assistant.busy, scroll)
</script>

<template>
  <div class="page-header">
    <div>
      <h2>Assistant IA</h2>
      <p>Posez vos questions : il répond à partir des avis clients et tickets support de votre boutique.</p>
    </div>
    <button v-if="assistant.messages.length" class="btn ghost" @click="assistant.clear()">Effacer</button>
  </div>

  <section class="card chat">
    <div ref="log" class="chat-log">
      <div v-if="!assistant.messages.length" class="empty" style="margin: auto">
        <Sparkles :size="34" />
        <strong>Que voulez-vous savoir sur vos clients ?</strong>
        <div class="row wrap" style="justify-content: center; max-width: 640px">
          <button v-for="s in SUGGESTIONS" :key="s" class="btn sm" @click="ask(s)">{{ s }}</button>
        </div>
      </div>

      <div v-for="(m, i) in assistant.messages" :key="i" class="bubble" :class="m.role">
        <span :style="m.error ? 'color: var(--red)' : ''">{{ m.text }}</span>
        <div v-if="m.sources != null" class="muted" style="font-size: 12px; margin-top: 6px">
          Basé sur {{ m.sources }} extraits
        </div>
      </div>

      <div v-if="assistant.busy" class="bubble bot typing">
        <span></span><span></span><span></span>
      </div>
    </div>

    <form class="chat-input" @submit.prevent="ask()">
      <input
        v-model="question"
        class="input grow"
        placeholder="Votre question…"
        :disabled="assistant.busy"
        aria-label="Question"
      />
      <button class="btn primary" type="submit" :disabled="assistant.busy || !question.trim()">
        <Send :size="15" /> Envoyer
      </button>
    </form>
  </section>
</template>
