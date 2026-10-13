<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Users, Repeat, Gem, UserPlus } from 'lucide-vue-next'
import { usePeriod } from '../stores/period'
import { useUi } from '../stores/ui'
import { qs } from '../lib/api'
import { useQuery, useDebounced } from '../lib/useQuery'
import { donutOption } from '../lib/charts'
import { fmtXof, fmtInt, fmtPct, fmtDate } from '../lib/format'
import KpiCard from '../components/KpiCard.vue'
import Card from '../components/Card.vue'
import Segmented from '../components/Segmented.vue'
import DataTable from '../components/DataTable.vue'
import Pager from '../components/Pager.vue'
import Badge from '../components/Badge.vue'
import EChart from '../components/EChart.vue'
import ErrorBox from '../components/ErrorBox.vue'

const period = usePeriod()
const ui = useUi()
const router = useRouter()
const segment = ref('all')
const search = ref('')
const q = useDebounced(search)
const sort = ref('spent')
const dir = ref('desc')
const page = ref(1)
const pageSize = 20

const SEGMENT_MAP = {
  all: '',
  repeat: 'repeat',
  single: 'one_order',
  vip: 'high_value',
  new: '',
  inactive: 'at_risk',
}
const segments = [
  { value: 'all', label: 'Tous' },
  { value: 'repeat', label: 'Fidèles (2+ commandes)' },
  { value: 'single', label: 'Une seule commande' },
  { value: 'vip', label: 'VIP (high value)' },
  { value: 'new', label: 'Nouveaux (période)' },
  { value: 'inactive', label: 'Inactifs (180 j+)' },
]

const SEGMENT_LABELS = {
  champions: 'Champions',
  high_value: 'High value',
  repeat: 'Fidèle',
  one_order: 'Nouveau',
  at_risk: 'À risque',
  never_ordered: 'Inactif',
  other: 'Autre',
}
const SEGMENT_TONES = {
  champions: 'green',
  high_value: 'teal',
  repeat: 'primary',
  one_order: 'amber',
  at_risk: 'red',
  never_ordered: 'blue',
  other: '',
}
const segmentLabel = (s) => SEGMENT_LABELS[s] || s || '–'
const segmentTone = (s) => SEGMENT_TONES[s] || ''

const { data, loading, error, reload } = useQuery(() =>
  period.ready
    ? `/api/v1/customers/segments${qs({
        segment: SEGMENT_MAP[segment.value] || '',
        country: q.value || '',
        limit: pageSize,
      })}`
    : null,
)

watch([segment, q, () => period.from, () => period.to], () => (page.value = 1))

const s = computed(() => data.value?.summary)
const customers = computed(() => data.value?.customers || [])

const repeatRate = computed(() => {
  if (!customers.value.length) return 0
  const repeat = customers.value.filter((c) => (c.order_count || 0) >= 2).length
  return (repeat / customers.value.length) * 100
})

const newInPeriod = computed(() =>
  customers.value.filter((c) => (c.order_count || 0) === 1).length,
)
const returningInPeriod = computed(() =>
  customers.value.filter((c) => (c.order_count || 0) >= 2).length,
)

// Graphique RFM : répartition des segments
const segmentChart = computed(() => {
  const counts = {}
  for (const c of customers.value) {
    const key = c.segment || 'other'
    counts[key] = (counts[key] || 0) + 1
  }
  const entries = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
  if (!entries.length) return null
  return donutOption({
    items: entries.map(([k, v]) => ({ label: segmentLabel(k), value: v })),
    dark: ui.dark,
    money: false,
  })
})

function onSort(key) {
  if (sort.value === key) dir.value = dir.value === 'asc' ? 'desc' : 'asc'
  else {
    sort.value = key
    dir.value = 'desc'
  }
  page.value = 1
}

const columns = [
  { key: 'customer_id', label: 'Client', sortable: true },
  { key: 'country', label: 'Pays', sortable: true },
  { key: 'order_count', label: 'Commandes', num: true, sortable: true },
  { key: 'lifetime_value_xof', label: 'Total dépensé', num: true, sortable: true },
  { key: 'segment', label: 'Segment RFM' },
  { key: 'last_order_at', label: 'Dernière commande', sortable: true },
]

const initials = (id) =>
  String(id).replace(/[^A-Za-z0-9]/g, '').slice(0, 2).toUpperCase() || '?'
</script>

<template>
  <ErrorBox :message="error" @retry="reload" />

  <section class="g-kpi">
    <KpiCard label="Clients (segment)" :icon="Users" :value="fmtInt(s?.count)" :loading="loading && !data" />
    <KpiCard label="Taux de réachat" :icon="Repeat" color="#14B8A6" :value="fmtPct(repeatRate)" :loading="loading && !data" />
    <KpiCard label="Valeur vie moyenne" :icon="Gem" color="#F59E0B" :value="fmtXof(s?.avg_ltv_xof)" :loading="loading && !data" />
    <KpiCard label="Nouveaux (segment)" :icon="UserPlus" color="#EC4899" :value="fmtInt(newInPeriod)" :loading="loading && !data" />
    <KpiCard label="Clients fidèles" :icon="Repeat" color="#8B5CF6" :value="fmtInt(returningInPeriod)" :loading="loading && !data" />
  </section>

  <section class="g-2">
    <Card title="Répartition RFM" sub="Segments détectés">
      <div v-if="loading && !data" class="skeleton" style="height: 280px"></div>
      <EChart v-else-if="segmentChart" :option="segmentChart" height="280px" />
      <p v-else class="muted pad">Pas de segments à afficher.</p>
    </Card>

    <Card title="Filtres" sub="Affiner la sélection">
      <div class="col" style="gap: 14px">
        <div>
          <div class="muted" style="font-size: 12px; margin-bottom: 6px">Segment prédéfini</div>
          <Segmented v-model="segment" :options="segments" />
        </div>
        <div>
          <div class="muted" style="font-size: 12px; margin-bottom: 6px">Recherche</div>
          <span class="search" style="width: 100%">
            <Search :size="16" />
            <input v-model="search" class="input" placeholder="Pays" />
          </span>
        </div>
      </div>
    </Card>
  </section>

  <Card title="Clients" sub="Cliquez sur une ligne pour voir le détail" flush>
    <DataTable
      :columns="columns"
      :rows="customers"
      :loading="loading"
      :sort="sort"
      :dir="dir"
      row-key="customer_id"
      clickable
      @sort="onSort"
      @row-click="(r) => router.push({ name: 'customer', params: { id: r.customer_id } })"
    >
      <template #cell-customer_id="{ row, value }">
        <span class="row" style="gap: 10px">
          <span class="avatar" style="width: 32px; height: 32px; font-size: 12px">
            {{ initials(value) }}
          </span>
          <span>
            <strong>{{ value }}</strong><br />
            <span class="muted" style="font-size: 12px">{{ row.city || '–' }}</span>
          </span>
        </span>
      </template>
      <template #cell-country="{ value }"><Badge>{{ value || '–' }}</Badge></template>
      <template #cell-order_count="{ value }">{{ fmtInt(value) }}</template>
      <template #cell-lifetime_value_xof="{ value }"><strong>{{ fmtXof(value) }}</strong></template>
      <template #cell-segment="{ value }">
        <Badge :tone="segmentTone(value)">{{ segmentLabel(value) }}</Badge>
      </template>
      <template #cell-last_order_at="{ value }"><span class="muted">{{ fmtDate(value) }}</span></template>
    </DataTable>

    <Pager v-if="data" v-model:page="page" :page-size="pageSize" :total="s?.count || customers.length" />
  </Card>
</template>
