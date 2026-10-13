<script setup>
defineProps({ title: String, sub: String, flush: Boolean })
</script>

<template>
  <section class="card">
    <header v-if="title || $slots.actions" class="card-h">
      <div>
        <h3>{{ title }}</h3>
        <div v-if="sub" class="sub">{{ sub }}</div>
      </div>
      <div class="row"><slot name="actions" /></div>
    </header>
    <div class="card-b" :class="{ flush }"><slot /></div>
  </section>
</template>
