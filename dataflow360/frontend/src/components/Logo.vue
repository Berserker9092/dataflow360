<script setup>
const props = defineProps({
  size: { type: [Number, String], default: 40 },
  variant: { type: String, default: 'icon' }, // 'icon' → W.svg | 'full' → womatt.svg
})

const src = props.variant === 'full' ? '/womatt.svg' : '/W.svg'
</script>

<template>
  <img
    :src="src"
    :style="{ height: `${size}px`, width: 'auto' }"
    :alt="variant === 'full' ? 'Womatt' : 'W'"
  />
</template>
