<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Sun, Moon, Tv } from 'lucide-vue-next'
import PeriodPicker from './PeriodPicker.vue'
import { useUi } from '../stores/ui'

const route = useRoute()
const router = useRouter()
const ui = useUi()
const title = computed(() => route.meta.title || '')

async function tvMode() {
  await router.push({ name: 'live' })
  ui.setTv(true)
}
</script>

<template>
  <header class="topbar">
    <h1>{{ title }}</h1>
    <PeriodPicker v-if="route.meta.period" />
    <button class="btn icon" :title="ui.dark ? 'Thème clair' : 'Thème sombre'" aria-label="Changer de thème" @click="ui.toggleTheme()">
      <Sun v-if="ui.dark" :size="17" />
      <Moon v-else :size="17" />
    </button>
    <button class="btn" title="Affichage plein écran pour un écran de bureau" @click="tvMode"><Tv :size="16" /> Mode TV</button>
  </header>
</template>
