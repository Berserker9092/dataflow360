<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'

const props = defineProps({
  // Données : [{ name: 'Session start', value: 95600 }, ...]
  items: { type: Array, default: () => [] },
  height: { type: String, default: '360px' },
  dark: { type: Boolean, default: false },
})

// Palette de dégradés (style Coupler.io : violet → bleu → cyan → rose)
const PALETTE = [
  ['#5E35B1', '#7E57C2'],  // violet
  ['#1565C0', '#1E88E5'],  // bleu
  ['#0277BD', '#039BE5'],  // bleu clair
  ['#00897B', '#26A69A'],  // teal
  ['#D81B60', '#EC407A'],  // rose
  ['#6A1B9A', '#AB47BC'],  // pourpre
]

const option = computed(() => {
  const items = props.items || []
  const total = items[0]?.value || 1

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: props.dark ? '#1E1E2A' : '#FFFFFF',
      borderColor: props.dark ? '#2A2A3A' : '#E4E8F0',
      textStyle: { color: props.dark ? '#E8E8F0' : '#1A1F36' },
      formatter: (p) => {
        const pct = ((p.value / total) * 100).toFixed(2)
        return `<strong>${p.name}</strong><br/>${p.value.toLocaleString()} <span style="color:#697386">(${pct}%)</span>`
      },
    },
    series: [
      {
        type: 'funnel',
        left: '5%',
        right: '30%',
        top: 20,
        bottom: 20,
        minSize: '30%',
        maxSize: '100%',
        sort: 'descending',
        gap: 4,
        label: {
          show: true,
          position: 'inside',
          formatter: (p) => `${p.value.toLocaleString()}`,
          color: '#FFFFFF',
          fontSize: 15,
          fontWeight: 700,
          textShadowColor: 'rgba(0,0,0,.2)',
          textShadowBlur: 4,
        },
        labelLine: {
          show: true,
          length: 30,
          lineStyle: { width: 1.5, type: 'solid' },
        },
        itemStyle: {
          borderWidth: 0,
          shadowBlur: 12,
          shadowColor: 'rgba(0,0,0,.15)',
          shadowOffsetY: 4,
        },
        emphasis: {
          label: { fontSize: 17 },
        },
        data: items.map((item, i) => {
          const grad = PALETTE[i % PALETTE.length]
          return {
            name: item.name,
            value: item.value,
            itemStyle: {
              color: {
                type: 'linear',
                x: 0, y: 0, x2: 1, y2: 0,
                colorStops: [
                  { offset: 0, color: grad[0] },
                  { offset: 1, color: grad[1] },
                ],
              },
              shadowBlur: 12,
              shadowColor: grad[0] + '40',
              shadowOffsetY: 4,
            },
            label: {
              color: '#FFFFFF',
            },
          }
        }),
      },
    ],
  }
})
</script>

<template>
  <div class="funnel-wrap">
    <EChart :option="option" :height="height" />
    <!-- Liste des étapes à droite avec pourcentages -->
    <ul class="funnel-legend">
      <li v-for="(item, i) in items" :key="item.name">
        <span
          class="dot"
          :style="{
            background: `linear-gradient(135deg, ${PALETTE[i % PALETTE.length][0]}, ${PALETTE[i % PALETTE.length][1]})`
          }"
        ></span>
        <span class="name">{{ item.name }}</span>
        <span class="pct">
          {{ ((item.value / (items[0]?.value || 1)) * 100).toFixed(2) }}%
        </span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.funnel-wrap {
  display: grid;
  grid-template-columns: 1fr 200px;
  gap: 16px;
  align-items: center;
  position: relative;
}

.funnel-legend {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  font-size: 13px;
}

.funnel-legend li {
  display: grid;
  grid-template-columns: 16px 1fr auto;
  gap: 10px;
  align-items: center;
  color: var(--text);
}

.funnel-legend .dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(0,0,0,.15), inset 0 -2px 4px rgba(0,0,0,.15), inset 0 2px 4px rgba(255,255,255,.3);
}

.funnel-legend .name {
  font-weight: 500;
  color: var(--text);
}

.funnel-legend .pct {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
}

@media (max-width: 900px) {
  .funnel-wrap { grid-template-columns: 1fr; }
  .funnel-legend { flex-direction: row; flex-wrap: wrap; }
}
</style>
