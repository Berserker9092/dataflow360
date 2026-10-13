<script setup>
import VChart from 'vue-echarts'
import '../lib/echarts'

defineProps({ option: { type: Object, required: true }, height: { type: String, default: '300px' } })
</script>

<template>
  <VChart class="chart" :option="option" :style="{ height }" autoresize />
</template>
