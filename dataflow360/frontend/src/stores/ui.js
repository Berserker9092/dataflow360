import { defineStore } from 'pinia'

const read = (key, fallback) => {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    return fallback
  }
}
const write = (key, value) => {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* stockage indisponible */
  }
}

export const useUi = defineStore('ui', {
  state: () => ({
    theme: read('df360.theme', window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
    collapsed: read('df360.collapsed', '0') === '1',
    tv: false,
  }),
  getters: { dark: (s) => s.theme === 'dark' },
  actions: {
    applyTheme() {
      document.documentElement.dataset.theme = this.theme
    },
    toggleTheme() {
      this.theme = this.dark ? 'light' : 'dark'
      write('df360.theme', this.theme)
      this.applyTheme()
    },
    toggleSidebar() {
      this.collapsed = !this.collapsed
      write('df360.collapsed', this.collapsed ? '1' : '0')
    },
    async setTv(on) {
      this.tv = on
      try {
        if (on && document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen()
        if (!on && document.fullscreenElement) await document.exitFullscreen()
      } catch {
        /* plein écran refusé : le mode TV reste actif sans plein écran */
      }
    },
  },
})
