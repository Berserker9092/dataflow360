<script setup>
import { Inbox } from 'lucide-vue-next'

defineProps({ title: { type: String, default: 'Aucune donnée' }, text: String, icon: [Object, Function] })
</script>

<template>
  <div class="empty">
    <component :is="icon || Inbox" :size="34" />
    <strong>{{ title }}</strong>
    <span v-if="text">{{ text }}</span>
    <slot />
  </div>
</template>
