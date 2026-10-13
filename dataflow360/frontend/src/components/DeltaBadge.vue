<script setup>
import { computed } from 'vue'
import { ArrowUpRight, ArrowDownRight } from 'lucide-vue-next'
import { fmtPct } from '../lib/format'

const props = defineProps({ value: Number })
const tone = computed(() => (props.value == null || props.value === 0 ? '' : props.value > 0 ? 'up' : 'down'))
</script>

<template>
  <span class="delta" :class="tone" :title="value == null ? 'Pas de période de comparaison' : ''">
    <ArrowUpRight v-if="tone === 'up'" :size="14" />
    <ArrowDownRight v-else-if="tone === 'down'" :size="14" />
    {{ fmtPct(value == null ? null : Math.abs(value)) }}
  </span>
</template>
