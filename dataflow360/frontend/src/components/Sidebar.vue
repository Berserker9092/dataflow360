<script setup>
import { LogOut, PanelLeftClose, PanelLeftOpen } from 'lucide-vue-next'
import { NAV } from '../router/nav'
import { useUi } from '../stores/ui'
import { useAuth } from '../stores/auth'
import { useBadges } from '../stores/badges'
import { useRouter } from 'vue-router'
import Logo from './Logo.vue'

const ui = useUi()
const auth = useAuth()
const badges = useBadges()
const router = useRouter()

function logout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <Logo :size="200" variant="icon" />
    </div>
    <div class="brand">
      <span class="brand-name">WOMATT</span>
    </div>


    <nav>
      <template v-for="group in NAV" :key="group.title">
        <div class="nav-title">{{ group.title }}</div>
        <router-link
          v-for="item in group.items"
          :key="item.name"
          :to="item.to"
          class="nav-link"
          :exact-active-class="item.to === '/' ? 'active' : ''"
          :active-class="item.to === '/' ? '' : 'active'"
          :title="item.label"
        >
          <component :is="item.icon" :size="19" />
          <span class="label">{{ item.label }}</span>
          <span v-if="item.badge && badges[item.badge] > 0" class="nav-badge">{{ badges[item.badge] }}</span>
        </router-link>
      </template>
    </nav>

    <div class="side-foot">
      <div v-if="auth.tenant" class="muted label" style="padding: 4px 10px 8px; font-size: 12px">
        Boutique<br /><strong style="color: var(--text)">{{ auth.tenant.name }}</strong>
      </div>
      <button class="nav-link" style="width: 100%; border: 0; background: none; cursor: pointer" title="Réduire le menu" @click="ui.toggleSidebar()">
        <component :is="ui.collapsed ? PanelLeftOpen : PanelLeftClose" :size="19" />
        <span class="label">Réduire le menu</span>
      </button>
      <button class="nav-link" style="width: 100%; border: 0; background: none; cursor: pointer" title="Se déconnecter" @click="logout">
        <LogOut :size="19" />
        <span class="label">Se déconnecter</span>
      </button>
    </div>
  </aside>
</template>
