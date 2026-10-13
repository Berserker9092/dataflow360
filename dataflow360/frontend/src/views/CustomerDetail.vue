<script setup>
import { computed } from 'vue'
import { ArrowLeft } from 'lucide-vue-next'
import { useUi } from '../stores/ui'
import { useQuery } from '../lib/useQuery'
import { barOption, hbarOption, COLORS } from '../lib/charts'
import { fmtXof, fmtInt, fmtDate, fmtDateTime, fmtMonth, statusLabel, statusTone } from '../lib/format'
import KpiCard from '../components/KpiCard.vue'
import Card from '../components/Card.vue'
import EChart from '../components/EChart.vue'
import DataTable from '../components/DataTable.vue'
import Badge from '../components/Badge.vue'
import ErrorBox from '../components/ErrorBox.vue'
import EmptyState from '../components/EmptyState.vue'

const props = defineProps({ id: String })
const ui = useUi()
const { data, loading, error, reload } = useQuery(() => `/api/v1/customers/${encodeURIComponent(props.id)}`)
const initials = computed(() => String(props.id).replace(/[^A-Za-z0-9]/g, '').slice(0, 2).toUpperCase() || '?')
const monthly = computed(() =>
  data.value
    ? barOption({ labels: data.value.monthly.labels.map(fmtMonth), data: data.value.monthly.revenue, dark: ui.dark, money: true, color: COLORS.primary })
    : null,
)
const products = computed(() =>
  hbarOption({ items: (data.value?.products || []).map((p) => ({ label: p.product_id, value: p.revenue })), dark: ui.dark, color: COLORS.teal }),
)
const columns = [
  { key: 'order_id', label: 'Commande' },
  { key: 'date', label: 'Date' },
  { key: 'status', label: 'Statut' },
  { key: 'total', label: 'Montant', num: true },
]
</script>

<template>
  <router-link to="/customers" class="muted row" style="width: fit-content"><ArrowLeft :size="15" /> Retour aux clients</router-link>
  <ErrorBox :message="error" @retry="reload" />

  <Card v-if="data || loading">
    <div class="row">
      <span class="avatar" style="width: 56px; height: 56px; font-size: 18px">{{ initials }}</span>
      <div>
        <h2 style="font-size: 20px">{{ id }}</h2>
        <p class="muted">{{ [data?.city, data?.country].filter(Boolean).join(' · ') || 'Localisation inconnue' }}</p>
      </div>
    </div>
  </Card>

  <section class="g-kpi">
    <KpiCard label="Total dépensé" :value="fmtXof(data?.spent)" :loading="loading && !data" />
    <KpiCard label="Commandes" :value="fmtInt(data?.orders)" :loading="loading && !data" color="#14B8A6" />
    <KpiCard label="Panier moyen" :value="fmtXof(data?.aov)" :loading="loading && !data" color="#F59E0B" />
    <KpiCard label="Première commande" :value="fmtDate(data?.first_order)" :loading="loading && !data" color="#8B5CF6" />
    <KpiCard label="Dernière commande" :value="fmtDate(data?.last_order)" :loading="loading && !data" color="#EC4899" />
  </section>

  <section v-if="data" class="g-2">
    <Card title="Dépenses par mois"><EChart :option="monthly" height="260px" /></Card>
    <Card title="Produits achetés" sub="Par chiffre d'affaires">
      <EmptyState v-if="!data.products.length" text="Aucun achat." />
      <EChart v-else :option="products" height="260px" />
    </Card>
  </section>

  <Card v-if="data" title="Dernières commandes" flush>
    <DataTable :columns="columns" :rows="data.orders_list" row-key="order_id">
      <template #cell-order_id="{ value }"><strong>{{ value }}</strong></template>
      <template #cell-date="{ value }"><span class="muted">{{ fmtDateTime(value) }}</span></template>
      <template #cell-status="{ value }"><Badge :tone="statusTone(value)">{{ statusLabel(value) }}</Badge></template>
      <template #cell-total="{ value }"><strong>{{ fmtXof(value) }}</strong></template>
    </DataTable>
  </Card>
</template>
