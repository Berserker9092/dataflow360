<script setup>
import { AlertTriangle, RefreshCw } from 'lucide-vue-next'

defineProps({ message: String })
defineEmits(['retry'])
</script>

<template>
  <div v-if="message" class="alert" role="alert">
    <AlertTriangle :size="18" />
    <span class="grow">{{ message }}</span>
    <button class="btn sm" @click="$emit('retry')"><RefreshCw :size="14" /> Réessayer</button>
  </div>
</template>
