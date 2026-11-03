<script setup lang="ts">
defineProps<{ companies: string[] }>()
const model = defineModel<string | null>({ required: true })
</script>

<template>
  <main class="flex min-h-screen items-center justify-center bg-navy-950 px-6">
    <section class="w-full max-w-md">
      <p class="text-sm font-medium uppercase tracking-widest text-navy-100/70">
        Skill Gap &amp; Growth Advisor
      </p>
      <h1 class="mt-3 text-3xl font-semibold text-white">Welk bedrijf ben je?</h1>
      <p class="mt-2 text-sm text-navy-100/80">
        Kies je bedrijf om de skill-kloof met de peer-groep te laden.
      </p>

      <label for="company" class="sr-only">Bedrijf</label>
      <select
        id="company"
        v-model="model"
        class="mt-8 w-full rounded-lg border border-navy-500 bg-white px-4 py-3 text-base text-slate-900 focus:outline-2 focus:outline-offset-2 focus:outline-navy-100"
      >
        <option :value="null" disabled>Selecteer een bedrijf…</option>
        <option v-for="company in companies" :key="company" :value="company">
          {{ company }}
        </option>
      </select>
    </section>
  </main>
</template>
