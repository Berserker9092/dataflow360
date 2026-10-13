<script setup>
import { computed, ref, watch } from 'vue'
import { TrendingUp, Trophy, Package } from 'lucide-vue-next'
import { useUi } from '../stores/ui'
import { useQuery } from '../lib/useQuery'
import { lineOption, hbarOption, COLORS } from '../lib/charts'
import { fmtInt, fmtDayShort } from '../lib/format'
import KpiCard from '../components/KpiCard.vue'
import Card from '../components/Card.vue'
import EChart from '../components/EChart.vue'
import ErrorBox from '../components/ErrorBox.vue'
import EmptyState from '../components/EmptyState.vue'

const ui = useUi()

// Route qui existe : liste des produits ayant une prévision
const products = useQuery(() => '/api/v1/forecast/products')

// Produit sélectionné (par défaut : le premier)
const product = ref('')
watch(
  () => products.data.value,
  (list) => {
    if (list?.length && !product.value) product.value = list[0]
  },
  { immediate: true },
)

// Détail du produit sélectionné (historique + prévision)
const detail = useQuery(() =>
  product.value ? `/api/v1/forecast/${encodeURIComponent(product.value)}` : null,
)

// KPI calculés depuis le détail
const totalForecast = computed(() => {
  const d = detail.data.value
  if (!d?.forecast) return 0
  return d.forecast.reduce((a, b) => a + (b.predicted_units || 0), 0)
})
const totalHistory = computed(() => {
  const d = detail.data.value
  if (!d?.history) return 0
  return d.history.reduce((a, b) => a + (b.units || 0), 0)
})
const avgDaily = computed(() => {
  const d = detail.data.value
  if (!d?.forecast?.length) return 0
  return Math.round(totalForecast.value / d.forecast.length)
})

// Graphique : historique + prévision en continuité
const productChart = computed(() => {
  const d = detail.data.value
  if (!d) return null
  const labels = [
    ...d.history.map((h) => h.date),
    ...d.forecast.map((f) => f.date),
  ]
  const hist = [
    ...d.history.map((h) => h.units),
    ...d.forecast.map(() => null),
  ]
  const fc = [
    ...d.history.map(() => null),
    ...d.forecast.map((f) => f.predicted_units),
  ]
  // Continuité : la prévision démarre au dernier point historique
  if (d.history.length && fc.length > d.history.length) {
    fc[d.history.length - 1] = d.history[d.history.length - 1].units
  }
  return lineOption({
    labels,
    series: [
      { name: 'Historique', data: hist, color: COLORS.primary },
      { name: 'Prévision', data: fc, color: COLORS.amber },
    ],
    dark: ui.dark,
    money: false,
  })
})

// Top 10 des produits (par unités prévues)
const topProducts = computed(() => {
  const list = products.data.value || []
  return list.slice(0, 10)
})
</script>

<template>
  <ErrorBox
    :message="products.error.value || detail.error.value"
    @retry="() => { products.reload(); detail.reload() }"
  />

  <section class="g-kpi">
    <KpiCard
      label="Produits avec prévision"
      :icon="Package"
      :value="fmtInt((products.data.value || []).length)"
      :loading="products.loading.value && !products.data.value"
    />
    <KpiCard
      label="Unités prévues"
      :icon="TrendingUp"
      color="#F59E0B"
      :value="fmtInt(totalForecast)"
      :loading="detail.loading.value && !detail.data.value"
    />
    <KpiCard
      label="Unités historiques"
      :icon="Trophy"
      color="#14B8A6"
      :value="fmtInt(totalHistory)"
      :loading="detail.loading.value && !detail.data.value"
    />
    <KpiCard
      label="Moyenne / jour prévue"
      :icon="TrendingUp"
      color="#8B5CF6"
      :value="fmtInt(avgDaily)"
      :loading="detail.loading.value && !detail.data.value"
    />
  </section>

  <Card title="Prévisions par produit" :sub="product ? `Produit sélectionné : ${product}` : 'Aucun produit'">
    <template #actions>
      <select v-if="products.data.value?.length" v-model="product" class="input">
        <option v-for="p in products.data.value" :key="p" :value="p">{{ p }}</option>
      </select>
    </template>
    <EmptyState v-if="!products.data.value?.length && !products.loading.value" text="Aucune prévision disponible. Lancez le modèle XGBoost." />
    <div v-else-if="detail.loading.value && !detail.data.value" class="skeleton" style="height: 360px"></div>
    <EChart v-else-if="productChart" :option="productChart" height="360px" />
    <EmptyState v-else text="Sélectionnez un produit." />
  </Card>

  <Card title="Top produits prévus" sub="Unités prévues" flush>
    <EmptyState v-if="!topProducts.length" text="Aucune prévision disponible." />
    <table v-else class="table">
      <thead>
        <tr>
          <th>#</th>
          <th>Produit</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(p, i) in topProducts" :key="p">
          <td>{{ i + 1 }}</td>
          <td class="mono">{{ p }}</td>
        </tr>
      </tbody>
    </table>
  </Card>
</template>
