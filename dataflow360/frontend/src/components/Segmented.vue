<script setup>
defineProps({ modelValue: String, options: { type: Array, required: true } })
defineEmits(['update:modelValue'])
</script>

<template>
  <div class="seg" role="tablist">
    <button
      v-for="o in options"
      :key="o.value"
      :class="{ on: modelValue === o.value }"
      role="tab"
      @click="$emit('update:modelValue', o.value)"
    >
      {{ o.label }}
    </button>
  </div>
</template>
