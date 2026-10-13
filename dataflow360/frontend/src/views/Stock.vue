<script setup>
import { computed, ref, watch } from 'vue'
import { Search, Boxes, AlertTriangle, PackageX, CheckCircle2 } from 'lucide-vue-next'
import { useQuery } from '../lib/useQuery'
import { fmtInt, fmtDec } from '../lib/format'
import KpiCard from '../components/KpiCard.vue'
import Card from '../components/Card.vue'
import Segmented from '../components/Segmented.vue'
import DataTable from '../components/DataTable.vue'
import Pager from '../components/Pager.vue'
import Badge from '../components/Badge.vue'
import ErrorBox from '../components/ErrorBox.vue'

const { data, loading, error, reload } = useQuery(() => '/api/v1/stock/status?limit=2000', { poll: 30000 })
const filter = ref('all')
const search = ref('')
const page = ref(1)
const pageSize = 20
const options = [
  { value: 'all', label: 'Tous' },
  { value: 'RUPTURE', label: 'Ruptures' },
  { value: 'ALERTE', label: 'Alertes' },
  { value: 'OK', label: 'OK' },
]
const rows = computed(() =>
  (data.value || []).filter(
    (r) =>
      (filter.value === 'all' || r.status === filter.value) &&
      (!search.value || `${r.product_id} ${r.category || ''}`.toLowerCase().includes(search.value.toLowerCase())),
  ),
)
const count = (status) => (data.value || []).filter((r) => r.status === status).length
const pageRows = computed(() => rows.value.slice((page.value - 1) * pageSize, page.value * pageSize))
watch([filter, search], () => (page.value = 1))

const TONE = { OK: 'green', ALERTE: 'amber', RUPTURE: 'red' }
const LABEL = { OK: 'OK', ALERTE: 'Alerte', RUPTURE: 'Rupture' }
const barColor = (s) => ({ OK: 'var(--green)', ALERTE: 'var(--amber)', RUPTURE: 'var(--red)' })[s]
const fill = (r) => Math.min(100, (r.stock_quantity / Math.max(1, r.stock_alert_threshold * 3)) * 100)
const columns = [
  { key: 'product_id', label: 'Produit' },
  { key: 'category', label: 'Catégorie' },
  { key: 'stock_quantity', label: 'Niveau de stock' },
  { key: 'stock_alert_threshold', label: 'Seuil', num: true },
  { key: 'days_of_cover', label: 'Jours de couverture', num: true },
  { key: 'status', label: 'Statut' },
]
</script>

<template>
  <ErrorBox :message="error" @retry="reload" />
  <section class="g-kpi">
    <KpiCard label="Produits suivis" :icon="Boxes" :value="fmtInt(data?.length)" :loading="loading && !data" />
    <KpiCard label="En rupture" :icon="PackageX" color="#EF4444" :value="fmtInt(count('RUPTURE'))" :loading="loading && !data" />
    <KpiCard label="Sous le seuil d'alerte" :icon="AlertTriangle" color="#F59E0B" :value="fmtInt(count('ALERTE'))" :loading="loading && !data" />
    <KpiCard label="Stock sain" :icon="CheckCircle2" color="#16A34A" :value="fmtInt(count('OK'))" :loading="loading && !data" />
  </section>

  <Card flush>
    <div class="row wrap" style="padding: 16px 18px">
      <Segmented v-model="filter" :options="options" />
      <span class="grow"></span>
      <span class="search"><Search :size="16" /><input v-model="search" class="input" placeholder="Produit ou catégorie" /></span>
    </div>
    <DataTable :columns="columns" :rows="pageRows" :loading="loading" row-key="product_id" empty-text="Aucun produit dans cette catégorie.">
      <template #cell-product_id="{ value }"><strong>{{ value }}</strong></template>
      <template #cell-stock_quantity="{ row, value }">
        <div class="row" style="gap: 12px">
          <div class="progress" style="width: 130px"><i :style="{ width: fill(row) + '%', background: barColor(row.status) }"></i></div>
          <strong class="mono">{{ fmtInt(value) }}</strong>
        </div>
      </template>
      <template #cell-days_of_cover="{ value }">
        <span v-if="value == null" class="faint" title="Aucune prévision pour ce produit (dev.bat train)">–</span>
        <strong v-else :style="{ color: value < 7 ? 'var(--red)' : value < 14 ? 'var(--amber)' : 'inherit' }">{{ fmtDec(value) }} j</strong>
      </template>
      <template #cell-status="{ value }"><Badge :tone="TONE[value]">{{ LABEL[value] }}</Badge></template>
    </DataTable>
    <Pager v-model:page="page" :page-size="pageSize" :total="rows.length" />
  </Card>
</template>
