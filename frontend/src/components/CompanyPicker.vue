<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ companies: string[]; loadError?: string | null }>()
const model = defineModel<string | null>({ required: true })

const query = ref('')
const error = ref('')

// Suggesties: eerst de bedrijven die beginnen met de getypte tekst, daarna de overige
// die de tekst ergens bevatten. Maximaal 50 tegelijk.
const suggestions = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return props.companies.slice(0, 50)
  const prefix = props.companies.filter((c) => c.toLowerCase().startsWith(q))
  const contains = props.companies.filter(
    (c) => !c.toLowerCase().startsWith(q) && c.toLowerCase().includes(q),
  )
  return [...prefix, ...contains].slice(0, 50)
})

// Alleen een bedrijf uit de databank is geldig, zodat Slice 1 een herkenbare naam krijgt.
function choose(): void {
  const q = query.value.trim().toLowerCase()
  const match = props.companies.find((c) => c.toLowerCase() === q)
  if (!match) {
    error.value = 'Kies een bedrijf uit de suggesties.'
    return
  }
  error.value = ''
  model.value = match
}
</script>

<template>
  <main class="flex min-h-screen items-center justify-center bg-navy-950 px-6">
    <section class="w-full max-w-md">
      <p class="text-sm font-medium uppercase tracking-widest text-navy-100/70">
        Skill Gap &amp; Growth Advisor
      </p>
      <h1 class="mt-3 text-3xl font-semibold text-white">Welk bedrijf ben je?</h1>
      <p class="mt-2 text-sm text-navy-100/80">
        Typ je bedrijfsnaam en kies er één uit de suggesties.
      </p>

      <form class="mt-8 space-y-3" @submit.prevent="choose">
        <label for="company" class="sr-only">Bedrijf</label>
        <input
          id="company"
          v-model="query"
          list="company-options"
          type="search"
          autocomplete="off"
          placeholder="Typ je bedrijfsnaam…"
          :aria-invalid="error ? 'true' : 'false'"
          aria-describedby="company-error"
          class="w-full rounded-lg border border-navy-500 bg-white px-4 py-3 text-base text-slate-900 focus:outline-2 focus:outline-offset-2 focus:outline-navy-100"
        />
        <datalist id="company-options">
          <option v-for="company in suggestions" :key="company" :value="company" />
        </datalist>
        <p v-if="loadError" class="text-sm text-red-200">
          Bedrijvenlijst niet geladen: {{ loadError }}
        </p>
        <p id="company-error" class="min-h-5 text-sm text-amber-200">{{ error }}</p>
        <button
          type="submit"
          class="w-full rounded-lg bg-white px-4 py-3 text-base font-medium text-navy-900 hover:bg-navy-100"
        >
          Analyseer mijn bedrijf
        </button>
      </form>
    </section>
  </main>
</template>
