<script setup>
import { computed, ref, watch } from 'vue'
import { Search, Download } from 'lucide-vue-next'
import { usePeriod } from '../stores/period'
import { qs } from '../lib/api'
import { useQuery, useDebounced } from '../lib/useQuery'
import { fmtXof, fmtInt, fmtDate, statusLabel } from '../lib/format'
import KpiCard from '../components/KpiCard.vue'
import Card from '../components/Card.vue'
import DataTable from '../components/DataTable.vue'
import Pager from '../components/Pager.vue'
import Badge from '../components/Badge.vue'
import ErrorBox from '../components/ErrorBox.vue'

const period = usePeriod()
const search = ref('')
const q = useDebounced(search)
const status = ref('all')
const sort = ref('date')
const dir = ref('desc')
const page = ref(1)
const pageSize = 25

const statuses = [
  { value: 'all', label: 'Tous les statuts' },
  { value: 'delivered', label: 'Livrée' },
  { value: 'shipped', label: 'Expédiée' },
  { value: 'processing', label: 'En préparation' },
  { value: 'invoiced', label: 'Validée' },
  { value: 'canceled', label: 'Annulée' },
  { value: 'unavailable', label: 'Indisponible' },
]

const { data, loading, error, reload } = useQuery(() =>
  period.ready
    ? `/api/v1/orders${qs({
        from: period.from,
        to: period.to,
        status: status.value,
        q: q.value || '',
        sort: sort.value,
        dir: dir.value,
        page: page.value,
        page_size: pageSize,
      })}`
    : null,
)

watch([status, q, () => period.from, () => period.to], () => (page.value = 1))

const rows = computed(() => data.value?.items || [])
const total = computed(() => data.value?.total || 0)

// Comptage par statut sur la page actuelle
const deliveredCount = computed(() => rows.value.filter((r) => r.status === 'delivered').length)
const canceledCount = computed(() => rows.value.filter((r) => r.status === 'canceled').length)
const totalAmount = computed(() => rows.value.reduce((s, r) => s + (r.amount || 0), 0))

function onSort(key) {
  if (sort.value === key) dir.value = dir.value === 'asc' ? 'desc' : 'asc'
  else {
    sort.value = key
    dir.value = 'desc'
  }
  page.value = 1
}

const columns = [
  { key: 'order_id', label: 'Commande' },
  { key: 'date', label: 'Date', sortable: true },
  { key: 'customer_id', label: 'Client' },
  { key: 'status', label: 'Statut', sortable: true },
  { key: 'items', label: 'Articles', num: true },
  { key: 'amount', label: 'Montant', num: true, sortable: true },
]

function exportCsv() {
  window.open(`/api/v1/orders/export${qs({ from: period.from, to: period.to, status: status.value })}`, '_blank')
}

const shortId = (id) => String(id || '').slice(0, 12) + '…'
</script>

<template>
  <ErrorBox :message="error" @retry="reload" />

  <section class="g-kpi">
    <KpiCard label="Commandes" :value="fmtInt(total)" :loading="loading && !data" />
    <KpiCard label="CA page" color="#14B8A6" :value="fmtXof(totalAmount)" :loading="loading && !data" />
    <KpiCard label="Livrées (page)" color="#16A34A" :value="fmtInt(deliveredCount)" :loading="loading && !data" />
    <KpiCard label="Annulées (page)" color="#EF4444" :value="fmtInt(canceledCount)" :loading="loading && !data" />
  </section>

  <Card flush>
    <div class="row wrap" style="padding: 16px 18px; gap: 10px">
      <span class="search">
        <Search :size="16" />
        <input v-model="search" class="input" placeholder="N° commande ou client" />
      </span>
      <select v-model="status" class="input" style="width: auto">
        <option v-for="s in statuses" :key="s.value" :value="s.value">{{ s.label }}</option>
      </select>
      <span class="grow"></span>
      <button class="btn" @click="exportCsv">
        <Download :size="14" /> Exporter CSV
      </button>
    </div>

    <DataTable
      :columns="columns"
      :rows="rows"
      :loading="loading"
      :sort="sort"
      :dir="dir"
      row-key="order_id"
      @sort="onSort"
    >
      <template #cell-order_id="{ value }">
        <span class="mono" :title="value">{{ shortId(value) }}</span>
      </template>
      <template #cell-date="{ value }"><span class="muted">{{ fmtDate(value) }}</span></template>
      <template #cell-customer_id="{ value }">
        <span class="mono">{{ shortId(value) }}</span>
      </template>
      <template #cell-status="{ value }">
        <Badge :tone="value === 'canceled' ? 'red' : value === 'delivered' ? 'green' : 'amber'">
          {{ statusLabel(value) }}
        </Badge>
      </template>
      <template #cell-items="{ value }">{{ fmtInt(value) }}</template>
      <template #cell-amount="{ value }"><strong>{{ fmtXof(value) }}</strong></template>
    </DataTable>

    <Pager v-if="data" v-model:page="page" :page-size="pageSize" :total="total" />
  </Card>
</template>


