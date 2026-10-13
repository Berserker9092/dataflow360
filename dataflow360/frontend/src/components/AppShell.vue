<template>
  <div class="shell">
    <Sidebar />
    <main class="main">
      <Topbar />
      <router-view />
    </main>
  </div>
</template>

<script setup>
import Sidebar from './Sidebar.vue'
import Topbar from './Topbar.vue'
</script>
