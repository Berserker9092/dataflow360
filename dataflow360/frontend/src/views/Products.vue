<script setup>
import { computed } from 'vue'
import { Package, Tag } from 'lucide-vue-next'
import { useUi } from '../stores/ui'
import { useQuery } from '../lib/useQuery'
import { hbarOption, donutOption, COLORS } from '../lib/charts'
import { fmtXof, fmtInt } from '../lib/format'
import KpiCard from '../components/KpiCard.vue'
import Card from '../components/Card.vue'
import EChart from '../components/EChart.vue'
import DataTable from '../components/DataTable.vue'
import ErrorBox from '../components/ErrorBox.vue'
import EmptyState from '../components/EmptyState.vue'

const ui = useUi()

const topProducts = useQuery(() => '/api/v1/kpi/top-products?limit=50')
const byCategory = useQuery(() => '/api/v1/kpi/by-category')

const products = computed(() => topProducts.data.value || [])
const categories = computed(() => byCategory.data.value || [])

const totalRevenue = computed(() => products.value.reduce((s, p) => s + (p.revenue_xof || 0), 0))
const totalUnits = computed(() => products.value.reduce((s, p) => s + (p.units_sold || 0), 0))
const avgPrice = computed(() => (totalUnits.value ? totalRevenue.value / totalUnits.value : 0))

const columns = [
  { key: 'product_id', label: 'ID' },
  { key: 'product_name', label: 'Produit' },
  { key: 'category', label: 'Catégorie' },
  { key: 'units_sold', label: 'Unités', num: true },
  { key: 'revenue_xof', label: 'CA (XOF)', num: true },
]

const categoryChart = computed(() => {
  if (!categories.value.length) return null
  return donutOption({
    items: categories.value.map((c) => ({ label: c.category, value: c.revenue_xof })),
    dark: ui.dark,
  })
})

const topChart = computed(() => {
  if (!products.value.length) return null
  return hbarOption({
    items: products.value.slice(0, 10).map((p) => ({
      label: p.product_name || p.product_id,
      value: p.revenue_xof,
    })),
    dark: ui.dark,
    color: COLORS.teal,
  })
})
</script>

<template>
  <ErrorBox :message="topProducts.error.value || byCategory.error.value" @retry="() => { topProducts.reload(); byCategory.reload() }" />

  <section class="g-kpi">
    <KpiCard label="Produits vendus" :icon="Package" :value="fmtInt(products.length)" :loading="topProducts.loading.value && !topProducts.data.value" />
    <KpiCard label="Unités totales" :icon="Package" color="#14B8A6" :value="fmtInt(totalUnits)" :loading="topProducts.loading.value && !topProducts.data.value" />
    <KpiCard label="CA cumulé" :icon="Tag" color="#F59E0B" :value="fmtXof(totalRevenue)" :loading="topProducts.loading.value && !topProducts.data.value" />
    <KpiCard label="Prix moyen unitaire" :icon="Tag" color="#8B5CF6" :value="fmtXof(avgPrice)" :loading="topProducts.loading.value && !topProducts.data.value" />
  </section>

  <section class="g-2">
    <Card title="Top 10 produits" sub="Chiffre d'affaires">
      <EmptyState v-if="products && !products.length" text="Aucune vente." />
      <EChart v-else-if="topChart" :option="topChart" height="360px" />
    </Card>
    <Card title="Répartition par catégorie" sub="Chiffre d'affaires">
      <EmptyState v-if="categories && !categories.length" text="Aucune catégorie." />
      <EChart v-else-if="categoryChart" :option="categoryChart" height="360px" />
    </Card>
  </section>

  <Card title="Performance produits" flush>
    <DataTable :columns="columns" :rows="products" row-key="product_id" empty-text="Aucune donnée.">
      <template #cell-product_name="{ value }"><strong>{{ value }}</strong></template>
      <template #cell-units_sold="{ value }">{{ fmtInt(value) }}</template>
      <template #cell-revenue_xof="{ value }">{{ fmtXof(value) }}</template>
    </DataTable>
  </Card>
</template>
