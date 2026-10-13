<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'
import DeltaBadge from './DeltaBadge.vue'
import { sparkOption, COLORS } from '../lib/charts'

const props = defineProps({
  label: String,
  value: String,
  delta: { type: Number, default: null },
  hasCompare: Boolean,
  previous: String,
  spark: { type: Array, default: () => [] },
  color: { type: String, default: COLORS.primary },
  icon: [Object, Function],
  loading: Boolean,
})
const option = computed(() => sparkOption({ data: props.spark, color: props.color }))
</script>

<template>
  <div class="card kpi">
    <div class="kpi-top">
      <span>{{ label }}</span>
      <span v-if="icon" class="kpi-icon" :style="{ color, background: color + '1f' }"><component :is="icon" :size="16" /></span>
    </div>
    <template v-if="loading">
      <div class="skeleton" style="height: 30px; width: 70%"></div>
      <div class="skeleton" style="height: 18px; width: 45%"></div>
    </template>
    <template v-else>
      <div class="kpi-value mono">{{ value }}</div>
      <div class="kpi-foot">
        <DeltaBadge v-if="hasCompare" :value="delta" />
        <span v-if="hasCompare && previous">vs {{ previous }}</span>
      </div>
    </template>
    <EChart v-if="spark.length > 1 && !loading" class="kpi-spark" :option="option" height="38px" />
  </div>
</template>
