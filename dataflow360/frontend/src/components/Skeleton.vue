<script setup>
defineProps({ height: { type: String, default: '16px' }, width: { type: String, default: '100%' } })
</script>

<template>
  <div class="skeleton" :style="{ height, width }"></div>
</template>
