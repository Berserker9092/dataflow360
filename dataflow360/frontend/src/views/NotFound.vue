<script setup>
import EmptyState from '../components/EmptyState.vue'
</script>

<template>
  <div class="login">
    <div class="card" style="padding: 24px">
      <EmptyState title="Page introuvable" text="Cette adresse n'existe pas dans le tableau de bord.">
        <router-link class="btn primary" to="/">Retour à la vue d'ensemble</router-link>
      </EmptyState>
    </div>
  </div>
</template>
