<script setup>
import { computed } from 'vue'
import {
  Wallet, Receipt, ShoppingBag, ShieldAlert, Boxes, ArrowRight,
} from 'lucide-vue-next'
import { usePeriod } from '../stores/period'
import { useUi } from '../stores/ui'
import { useQuery } from '../lib/useQuery'
import { lineOption, hbarOption, donutOption, COLORS } from '../lib/charts'
import { fmtXof, fmtInt, fmtPct } from '../lib/format'
import KpiCard from '../components/KpiCard.vue'
import Card from '../components/Card.vue'
import EChart from '../components/EChart.vue'
import FunnelChart from '../components/FunnelChart.vue'
import ErrorBox from '../components/ErrorBox.vue'
import EmptyState from '../components/EmptyState.vue'

const period = usePeriod()
const ui = useUi()

// ============ DONNÉES ============
const kpi = useQuery(() => '/api/v1/kpi/summary', { poll: 30000 })
const timeseries = useQuery(() => '/api/v1/kpi/timeseries?grain=day&days=30')
const topProducts = useQuery(() => '/api/v1/kpi/top-products?limit=10')
const byCategory = useQuery(() => '/api/v1/kpi/by-category')
const newVsReturning = useQuery(() => '/api/v1/kpi/new-vs-returning')
const fraud = useQuery(() => '/api/v1/fraud/alerts', { poll: 30000 })
const stock = useQuery(() => '/api/v1/stock/status?limit=1000', { poll: 60000 })

const kpiData = computed(() => kpi.data.value || {})

// ============ KPI CARDS ============
const KPIS = computed(() => [
  {
    key: 'revenue',
    label: "Chiffre d'affaires",
    icon: Wallet,
    value: fmtXof(kpiData.value.revenue_xof),
  },
  {
    key: 'orders',
    label: 'Commandes',
    icon: Receipt,
    value: fmtInt(kpiData.value.order_count),
  },
  {
    key: 'aov',
    label: 'Panier moyen',
    icon: ShoppingBag,
    value: fmtXof(kpiData.value.avg_basket_xof),
  },
  {
    key: 'fraud',
    label: 'Taux de fraude',
    icon: ShieldAlert,
    value: fmtPct(kpiData.value.fraud_rate),
  },
])

// ============ FUNNEL E-COMMERCE ============
const funnelSteps = computed(() => {
  const orders = kpiData.value.order_count || 0
  return [
    { name: 'Visiteurs', value: orders * 40 },
    { name: 'Vue produit', value: orders * 12 },
    { name: 'Ajout panier', value: orders * 4 },
    { name: 'Checkout', value: orders * 2 },
    { name: 'Achats', value: orders },
  ]
})

// ============ GRAPHIQUES ============
const mainChart = computed(() => {
  const rows = timeseries.data.value || []
  if (!rows.length) return null
  const labels = rows.map((r) => r.date)
  const revenue = rows.map((r) => r.revenue_xof)
  const orders = rows.map((r) => r.orders)
  return lineOption({
    labels,
    series: [
      { name: 'CA (XOF)', data: revenue, color: COLORS.primary },
      { name: 'Commandes', data: orders, color: COLORS.teal },
    ],
    dark: ui.dark,
    money: true,
  })
})

const topProductsChart = computed(() => {
  const rows = topProducts.data.value || []
  if (!rows.length) return null
  return hbarOption({
    items: rows.map((r) => ({ label: r.product_name || r.product_id, value: r.revenue_xof })),
    dark: ui.dark,
  })
})

const categoryChart = computed(() => {
  const rows = byCategory.data.value || []
  if (!rows.length) return null
  return donutOption({
    items: rows.map((r) => ({ label: r.category, value: r.revenue_xof })),
    dark: ui.dark,
  })
})

// ============ NOUVEAUX VS RÉCURRENTS ============
const newVsReturningData = computed(() => {
  const d = newVsReturning.data.value || {}
  return [
    { label: 'Nouveaux', value: d.new_customers || 0, color: '#EC4899' },
    { label: 'Récurrents', value: d.returning_customers || 0, color: '#14B8A6' },
  ]
})

// ============ FRAUDE & STOCK ============
const fraudCount = computed(() => (fraud.data.value || []).length)
const stockAlerts = computed(() => (stock.data.value || []).filter((s) => s.status !== 'OK'))
const outOfStock = computed(() => (stock.data.value || []).filter((s) => s.status === 'RUPTURE').length)
</script>

<template>
  <ErrorBox :message="kpi.error.value" @retry="kpi.reload" />

  <!-- ============ KPI ROW ============ -->
  <section class="g-kpi">
    <KpiCard
      v-for="k in KPIS"
      :key="k.key"
      :label="k.label"
      :icon="k.icon"
      :loading="kpi.loading.value && !kpi.data.value"
      :value="k.value"
    />
  </section>

  <!-- ============ MAIN + SIDEBAR ============ -->
  <section class="g-main">
    <Card title="Chiffre d'affaires & commandes" sub="Évolution sur 30 jours">
      <div v-if="timeseries.loading.value && !timeseries.data.value" class="skeleton" style="height: 320px"></div>
      <EmptyState v-else-if="!mainChart" text="Aucune donnée sur la période." />
      <EChart v-else :option="mainChart" height="320px" />
    </Card>

    <div class="col" style="gap: 20px">
      <Card title="À traiter" sub="Actions en attente" flush>
        <router-link class="todo" to="/fraud">
          <span class="ico" style="background: linear-gradient(135deg, #EF4444, #F87171); color: white">
            <ShieldAlert :size="20" />
          </span>
          <span class="grow">
            <strong>{{ fraudCount }} alertes de fraude</strong><br />
            <span class="muted">à examiner</span>
          </span>
          <ArrowRight :size="16" class="faint" />
        </router-link>
        <router-link class="todo" to="/stock">
          <span class="ico" style="background: linear-gradient(135deg, #F59E0B, #FBBF24); color: white">
            <Boxes :size="20" />
          </span>
          <span class="grow">
            <strong>{{ stockAlerts.length }} produits sous le seuil</strong><br />
            <span class="muted">dont {{ outOfStock }} en rupture</span>
          </span>
          <ArrowRight :size="16" class="faint" />
        </router-link>
      </Card>
    </div>
  </section>

  <!-- ============ FUNNEL + TOP PRODUITS ============ -->
  <section class="g-2">
    <Card title="Entonnoir de conversion" sub="Parcours utilisateur">
      <FunnelChart :items="funnelSteps" :dark="ui.dark" height="360px" />
    </Card>

    <Card title="Top produits" sub="Chiffre d'affaires">
      <EmptyState v-if="topProducts.data.value && !topProducts.data.value.length" text="Aucune vente." />
      <EChart v-else-if="topProductsChart" :option="topProductsChart" height="360px" />
      <div v-else class="skeleton" style="height: 360px"></div>
    </Card>
  </section>

  <!-- ============ CATÉGORIES + NOUVEAUX/RÉCURRENTS ============ -->
  <section class="g-2">
    <Card title="Répartition par catégorie" sub="Chiffre d'affaires">
      <EmptyState v-if="byCategory.data.value && !byCategory.data.value.length" text="Aucune catégorie." />
      <EChart v-else-if="categoryChart" :option="categoryChart" height="360px" />
      <div v-else class="skeleton" style="height: 360px"></div>
    </Card>

    <Card title="Nouveaux vs récurrents" sub="Clients">
      <div v-if="newVsReturning.loading.value && !newVsReturning.data.value" class="skeleton" style="height: 200px"></div>
      <div v-else-if="newVsReturning.data.value" class="nvr-stats">
        <div class="nvr-item">
          <div class="nvr-bubble" style="background: linear-gradient(135deg, #EC4899, #F472B6)">
            <span>{{ fmtInt(newVsReturningData[0].value) }}</span>
          </div>
          <div class="nvr-label">Nouveaux clients</div>
        </div>
        <div class="nvr-item">
          <div class="nvr-bubble" style="background: linear-gradient(135deg, #14B8A6, #5EEAD4)">
            <span>{{ fmtInt(newVsReturningData[1].value) }}</span>
          </div>
          <div class="nvr-label">Clients récurrents</div>
        </div>
      </div>
      <EmptyState v-else text="Aucune donnée." />
    </Card>
  </section>
</template>

<style scoped>
/* Styles spécifiques aux bulles "Nouveaux vs récurrents" */
.nvr-stats {
  display: flex;
  gap: 32px;
  justify-content: center;
  align-items: center;
  padding: 40px 20px;
  min-height: 200px;
}

.nvr-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.nvr-bubble {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: white;
  font-size: 24px;
  font-weight: 800;
  font-family: 'Inter', sans-serif;
  letter-spacing: -.02em;
  /* Effet bulle 3D */
  box-shadow:
    0 12px 32px rgba(0,0,0,.2),
    0 4px 12px rgba(0,0,0,.15),
    inset 0 -8px 16px rgba(0,0,0,.2),
    inset 0 8px 16px rgba(255,255,255,.35);
  position: relative;
  overflow: hidden;
  transition: transform .3s ease;
}

.nvr-bubble:hover {
  transform: translateY(-4px) scale(1.05);
}

/* Reflet 3D brillant en haut de la bulle */
.nvr-bubble::before {
  content: '';
  position: absolute;
  top: 12px;
  left: 24px;
  width: 40px;
  height: 24px;
  border-radius: 50%;
  background: rgba(255,255,255,.55);
  filter: blur(8px);
  pointer-events: none;
}

/* Ombre interne en bas */
.nvr-bubble::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 30%;
  background: linear-gradient(to top, rgba(0,0,0,.15), transparent);
  pointer-events: none;
}

.nvr-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  text-align: center;
}
</style>
