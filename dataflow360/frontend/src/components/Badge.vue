<script setup>
defineProps({ tone: { type: String, default: 'gray' } })
</script>

<template>
  <span class="badge" :class="tone"><slot /></span>
</template>
