<script setup>
import { computed } from 'vue'
import { Calendar } from 'lucide-vue-next'
import { usePeriod, PRESETS, COMPARES } from '../stores/period'
import { fmtDate } from '../lib/format'

const period = usePeriod()
const range = computed(() => `${fmtDate(period.from)} → ${fmtDate(period.to)}`)
</script>

<template>
  <div class="row wrap" style="gap: 8px">
    <div class="seg">
      <button
        v-for="p in PRESETS"
        :key="p.value"
        :class="{ on: period.preset === p.value }"
        @click="p.value === 'custom' ? (period.preset = 'custom') : period.applyPreset(p.value)"
      >
        {{ p.label }}
      </button>
    </div>
    <template v-if="period.preset === 'custom'">
      <input class="input" type="date" :value="period.from" :max="period.to" aria-label="Début" @change="period.setCustom($event.target.value, period.to)" />
      <input class="input" type="date" :value="period.to" :min="period.from" aria-label="Fin" @change="period.setCustom(period.from, $event.target.value)" />
    </template>
    <span v-else class="muted nowrap row" style="gap: 6px"><Calendar :size="15" /> {{ range }}</span>
    <select class="select" :value="period.compare" aria-label="Comparaison" @change="period.setCompare($event.target.value)">
      <option v-for="c in COMPARES" :key="c.value" :value="c.value">{{ c.label }}</option>
    </select>
  </div>
</template>
