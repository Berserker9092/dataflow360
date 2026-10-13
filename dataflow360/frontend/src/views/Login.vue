total 16
drwxrwxrwx 2 diop diop 4096 Oct  9 15:54 .
drwxrwxrwx 7 diop diop 4096 Oct  9 11:49 ..
-rw-rw-r-- 1 diop diop 3321 Oct  9 15:39 womatt.svg

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { KeyRound, ArrowRight } from 'lucide-vue-next'
import { useAuth } from '../stores/auth'
import ErrorBox from '../components/ErrorBox.vue'
import Logo from '../components/Logo.vue'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const key = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  if (key.value.trim().length < 8) {
    error.value = 'La clé API contient au moins 8 caractères.'
    return
  }
  busy.value = true
  error.value = ''
  try {
    await auth.login(key.value)
    router.push(typeof route.query.redirect === 'string' ? route.query.redirect : '/')
  } catch (e) {
    error.value =
      e.status === 401
        ? "Clé API inconnue de la base. Saisissez la valeur de DEMO_TENANT_KEY (.env.local), puis lancez « dev.bat bootstrap » : il enregistre cette clé."
        : e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <form class="card login-card" @submit.prevent="submit">
      <div class="row" style="gap: 12px; margin-bottom: 20px">
        <Logo :size="96" variant="full" />
      </div>
      <div>
        <h1>Connexion à WOMATT</h1>
        <p class="muted" style="margin-top: 4px">
          Saisissez la clé API de votre boutique pour accéder au tableau de bord.
        </p>
      </div>
      <label class="col" style="gap: 6px; margin-top: 16px">
        <span style="font-weight: 600">Clé API</span>
        <span class="search">
          <KeyRound :size="16" />
          <input
            v-model="key"
            class="input"
            style="width: 100%"
            type="password"
            autocomplete="off"
            placeholder="demo-key-…"
            autofocus
          />
        </span>
      </label>
      <ErrorBox :message="error" @retry="submit" />
      <button class="btn primary" style="height: 42px; margin-top: 12px" :disabled="busy" type="submit">
        {{ busy ? 'Vérification…' : 'Se connecter' }}
        <ArrowRight v-if="!busy" :size="16" />
      </button>
    </form>
  </div>
</template>
