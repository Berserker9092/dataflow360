<script setup>
import { computed, ref } from 'vue'
import { ShieldAlert, Ban, Check, X, ShieldCheck } from 'lucide-vue-next'
import { api } from '../lib/api'
import { useQuery } from '../lib/useQuery'
import { useBadges } from '../stores/badges'
import { fmtXof, fmtInt, fmtDateTime } from '../lib/format'
import KpiCard from '../components/KpiCard.vue'
import Card from '../components/Card.vue'
import Badge from '../components/Badge.vue'
import DataTable from '../components/DataTable.vue'
import ErrorBox from '../components/ErrorBox.vue'
import EmptyState from '../components/EmptyState.vue'

const badges = useBadges()
const alerts = useQuery(() => '/api/v1/fraud/alerts', { poll: 5000 })
const busy = ref('')
const actionError = ref('')

const alertList = computed(() => alerts.data.value || [])
const pending = computed(() => alertList.value.length)
const highRisk = computed(() => alertList.value.filter((a) => a.risk === 'ELEVE').length)
const totalAmount = computed(() =>
  alertList.value.reduce((sum, a) => sum + (a.amount || 0), 0),
)

async function decide(order, action) {
  busy.value = order
  actionError.value = ''
  try {
    await api.post('/api/v1/fraud/decision', { order_id: order, action })
    if (alerts.data.value) alerts.data.value = alerts.data.value.filter((a) => a.order_id !== order)
    await badges.refresh()
  } catch (e) {
    actionError.value = e.message
  } finally {
    busy.value = ''
  }
}

const level = (score) => (score >= 70 ? 'high' : 'mid')

const columns = [
  { key: 'order_id', label: 'Commande' },
  { key: 'score', label: 'Score', num: true },
  { key: 'risk', label: 'Risque' },
  { key: 'amount', label: 'Montant', num: true },
  { key: 'ts', label: 'Détectée le' },
]
</script>

<template>
  <ErrorBox :message="alerts.error.value || actionError" @retry="alerts.reload" />

  <section class="g-kpi">
    <KpiCard label="Alertes en attente" :icon="ShieldAlert" color="#EF4444" :value="fmtInt(pending)" :loading="alerts.loading.value && !alerts.data.value" />
    <KpiCard label="Risque élevé" :icon="ShieldAlert" color="#F59E0B" :value="fmtInt(highRisk)" :loading="alerts.loading.value && !alerts.data.value" />
    <KpiCard label="Montant à risque" :icon="Ban" color="#16A34A" :value="fmtXof(totalAmount)" :loading="alerts.loading.value && !alerts.data.value" />
    <KpiCard label="Total alertes" :icon="ShieldAlert" color="#6366F1" :value="fmtInt(alertList.length)" :loading="alerts.loading.value && !alerts.data.value" />
  </section>

  <Card title="Alertes à traiter" sub="Rafraîchi toutes les 5 secondes" flush>
    <EmptyState
      v-if="alerts.data.value && !alerts.data.value.length"
      title="Aucune alerte en attente"
      text="Les commandes suspectes apparaîtront ici dès qu'elles seront détectées."
      :icon="ShieldCheck"
    />
    <div v-for="a in alertList" :key="a.order_id" class="alert-item">
      <div class="score" :class="level(a.score)">{{ a.score }}</div>
      <div>
        <div class="row" style="gap: 8px">
          <strong>{{ a.order_id }}</strong>
          <Badge :tone="a.risk === 'ELEVE' ? 'red' : 'amber'">
            Risque {{ a.risk === 'ELEVE' ? 'élevé' : 'moyen' }}
          </Badge>
        </div>
        <div class="row wrap" style="gap: 6px; margin-top: 6px">
          <Badge v-for="r in a.reasons || []" :key="r" tone="primary">{{ r }}</Badge>
          <span v-if="a.ts" class="muted" style="font-size: 12px">{{ fmtDateTime(new Date(a.ts * 1000).toISOString()) }}</span>
        </div>
      </div>
      <div class="row">
        <button class="btn danger sm" :disabled="busy === a.order_id" @click="decide(a.order_id, 'BLOCK')">
          <X :size="14" /> Bloquer
        </button>
        <button class="btn success sm" :disabled="busy === a.order_id" @click="decide(a.order_id, 'PASS')">
          <Check :size="14" /> Laisser passer
        </button>
      </div>
    </div>
  </Card>

  <Card title="Historique des alertes actuelles" flush>
    <DataTable :columns="columns" :rows="alertList" row-key="order_id" empty-text="Aucune alerte.">
      <template #cell-order_id="{ value }"><strong>{{ value }}</strong></template>
      <template #cell-risk="{ value }"><Badge :tone="value === 'ELEVE' ? 'red' : 'amber'">{{ value }}</Badge></template>
      <template #cell-amount="{ value }">{{ fmtXof(value) }}</template>
      <template #cell-ts="{ value }">
        <span class="muted">{{ value ? fmtDateTime(new Date(value * 1000).toISOString()) : '–' }}</span>
      </template>
    </DataTable>
  </Card>
</template>
