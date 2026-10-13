<script setup>
import { computed } from 'vue'
import { Radio, ShieldAlert } from 'lucide-vue-next'
import { useUi } from '../stores/ui'
import { useQuery } from '../lib/useQuery'
import { barOption, COLORS } from '../lib/charts'
import { fmtXof, fmtInt, fmtTime } from '../lib/format'
import Card from '../components/Card.vue'
import EChart from '../components/EChart.vue'
import Badge from '../components/Badge.vue'
import ErrorBox from '../components/ErrorBox.vue'
import EmptyState from '../components/EmptyState.vue'

const ui = useUi()
const { data, error, reload } = useQuery(() => '/api/v1/live/feed?limit=14', { poll: 3000 })
const t = computed(() => data.value?.totals)
const chart = computed(() =>
  barOption({
    labels: (data.value?.series || []).map((s) => (s.minutes_ago === 0 ? 'now' : `-${s.minutes_ago}`)),
    data: (data.value?.series || []).map((s) => s.orders),
    dark: ui.dark,
    color: COLORS.teal,
    name: 'Commandes',
  }),
)
const STATUS = { approved: ['Validée', 'green'], pending: ['En attente', 'amber'], failed: ['Paiement refusé', 'red'] }
</script>

<template>
  <ErrorBox :message="error" @retry="reload" />
  <div class="page-header">
    <div class="row"><span class="dot"></span><h2>Activité en direct</h2></div>
    <router-link v-if="data?.pending_alerts" to="/fraud" class="badge red" style="padding: 6px 12px"><ShieldAlert :size="14" /> {{ data.pending_alerts }} alertes de fraude</router-link>
  </div>

  <section class="g-kpi">
    <div class="card kpi"><div class="kpi-top">Commandes · 5 dernières minutes</div><div class="big mono">{{ fmtInt(t?.orders_5m) }}</div></div>
    <div class="card kpi"><div class="kpi-top">Chiffre d'affaires · 5 min</div><div class="big mono">{{ fmtXof(t?.revenue_5m) }}</div></div>
    <div class="card kpi"><div class="kpi-top">Commandes · dernière heure</div><div class="big mono">{{ fmtInt(t?.orders_60m) }}</div></div>
    <div class="card kpi"><div class="kpi-top">Chiffre d'affaires · 1 heure</div><div class="big mono">{{ fmtXof(t?.revenue_60m) }}</div></div>
  </section>

  <section class="g-main">
    <Card title="Commandes par minute" sub="30 dernières minutes"><EChart :option="chart" height="300px" /></Card>
    <Card title="Dernières commandes" flush>
      <EmptyState v-if="data && !data.events.length" title="Aucune commande récente" text="Lancez le simulateur : dev.bat producer" :icon="Radio" />
      <div v-for="e in data?.events || []" :key="e.order_id + e.at" class="feed-item">
        <Badge :tone="(STATUS[e.status] || ['', 'gray'])[1]">{{ (STATUS[e.status] || [e.status])[0] }}</Badge>
        <div style="min-width: 0">
          <strong>{{ e.order_id }}</strong>
          <div class="muted" style="font-size: 12px">{{ e.customer_id }} · {{ e.country || '–' }} · {{ fmtTime(e.at) }}</div>
        </div>
        <div class="right">
          <strong class="mono">{{ fmtXof(e.amount) }}</strong>
          <div v-if="e.score != null"><Badge tone="red">Suspect · {{ e.score }}</Badge></div>
        </div>
      </div>
    </Card>
  </section>
</template>
