<script setup>
import { ArrowUp, ArrowDown } from 'lucide-vue-next'
import EmptyState from './EmptyState.vue'

defineProps({
  columns: { type: Array, required: true }, // { key, label, num?, sortable? }
  rows: { type: Array, default: () => [] },
  loading: Boolean,
  sort: String,
  dir: { type: String, default: 'desc' },
  rowKey: { type: String, default: 'id' },
  clickable: Boolean,
  emptyText: { type: String, default: 'Aucun résultat pour ces filtres.' },
})
const emit = defineEmits(['sort', 'row-click'])
</script>

<template>
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th
            v-for="c in columns"
            :key="c.key"
            :class="{ num: c.num, sortable: c.sortable }"
            @click="c.sortable && emit('sort', c.key)"
          >
            <span class="row" :style="{ justifyContent: c.num ? 'flex-end' : 'flex-start', gap: '4px' }">
              {{ c.label }}
              <template v-if="c.sortable && sort === c.key">
                <ArrowUp v-if="dir === 'asc'" :size="13" />
                <ArrowDown v-else :size="13" />
              </template>
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-if="loading && !rows.length">
          <tr v-for="n in 6" :key="n">
            <td v-for="c in columns" :key="c.key"><div class="skeleton" style="height: 14px"></div></td>
          </tr>
        </template>
        <tr
          v-for="r in rows"
          v-else
          :key="r[rowKey]"
          :class="{ click: clickable }"
          @click="clickable && emit('row-click', r)"
        >
          <td v-for="c in columns" :key="c.key" :class="{ num: c.num }">
            <slot :name="`cell-${c.key}`" :row="r" :value="r[c.key]">{{ r[c.key] ?? '–' }}</slot>
          </td>
        </tr>
      </tbody>
    </table>
    <EmptyState v-if="!loading && !rows.length" :text="emptyText" />
  </div>
</template>
