<script setup>
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { fmtInt } from '../lib/format'

const props = defineProps({ page: Number, pageSize: Number, total: Number })
const emit = defineEmits(['update:page'])
const pages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const from = computed(() => (props.total ? (props.page - 1) * props.pageSize + 1 : 0))
const to = computed(() => Math.min(props.total, props.page * props.pageSize))
</script>

<template>
  <div class="pager">
    <span>{{ fmtInt(from) }}–{{ fmtInt(to) }} sur {{ fmtInt(total) }}</span>
    <div class="row">
      <button class="btn sm icon" :disabled="page <= 1" aria-label="Page précédente" @click="emit('update:page', page - 1)">
        <ChevronLeft :size="16" />
      </button>
      <span class="mono">Page {{ page }} / {{ pages }}</span>
      <button class="btn sm icon" :disabled="page >= pages" aria-label="Page suivante" @click="emit('update:page', page + 1)">
        <ChevronRight :size="16" />
      </button>
    </div>
  </div>
</template>
