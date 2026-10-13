import {
  LayoutDashboard, ShoppingCart, Package, Users, Boxes, ShieldAlert, TrendingUp, Bot, Radio,
} from 'lucide-vue-next'

// Menu latéral : un seul endroit pour les libellés, icônes et regroupements.
export const NAV = [
  {
    title: 'Analyse',
    items: [
      { to: '/', name: 'overview', label: "Vue d'ensemble", icon: LayoutDashboard },
      { to: '/orders', name: 'orders', label: 'Commandes', icon: ShoppingCart },
      { to: '/products', name: 'products', label: 'Produits', icon: Package },
      { to: '/customers', name: 'customers', label: 'Clients', icon: Users },
    ],
  },
  {
    title: 'Opérations',
    items: [
      { to: '/stock', name: 'stock', label: 'Stocks', icon: Boxes },
      { to: '/fraud', name: 'fraud', label: 'Fraude', icon: ShieldAlert, badge: 'fraud' },
      { to: '/forecast', name: 'forecast', label: 'Prévisions', icon: TrendingUp },
    ],
  },
  {
    title: 'Outils',
    items: [
      { to: '/assistant', name: 'assistant', label: 'Assistant IA', icon: Bot },
      { to: '/live', name: 'live', label: 'Temps réel', icon: Radio },
    ],
  },
]
