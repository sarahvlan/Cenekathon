<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { SkillGapData, SkillGapResponse } from '@/types'
import { allSkills, buildAdvice, sortedTimelines, timelineLabel } from '@/lib/analysis'
import CompanyPicker from '@/components/CompanyPicker.vue'
import AdviceCard from '@/components/AdviceCard.vue'
import MarketTable from '@/components/MarketTable.vue'
import CompanyCard from '@/components/CompanyCard.vue'

// Doelbedrijven met een Slice 3-output (backend/output), en het gekozen doelbedrijf.
const targets = ref<string[]>([])
const target = ref<string | null>(null)
const data = ref<SkillGapData>({})
const loading = ref(false)
const error = ref<string | null>(null)

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  const body = await res.json()
  if (!res.ok) throw new Error(body.error ?? res.statusText)
  return body as T
}

onMounted(async () => {
  try {
    targets.value = await getJson<string[]>('/api/targets')
  } catch (e) {
    error.value = String(e)
  }
})

// Elke keuze van een doelbedrijf haalt de bijbehorende Slice 3-data op.
watch(target, async (name) => {
  if (!name) return
  loading.value = true
  error.value = null
  try {
    const res = await getJson<SkillGapResponse>(`/api/skill-gap?target=${encodeURIComponent(name)}`)
    data.value = res.data
  } catch (e) {
    data.value = {}
    error.value = String(e)
  } finally {
    loading.value = false
  }
})

const timelines = computed(() => sortedTimelines(data.value))
const skills = computed(() => allSkills(data.value))
// Het doelbedrijf heeft eigen tijdlijnen nodig om te kunnen vergelijken.
const hasTargetData = computed(
  () => !!target.value && Object.keys(data.value[target.value] ?? {}).length > 0,
)
const advice = computed(() =>
  target.value && hasTargetData.value ? buildAdvice(data.value, target.value) : [],
)
const peerNames = computed(() => Object.keys(data.value).filter((c) => c !== target.value))
</script>

<template>
  <CompanyPicker v-if="!target" v-model="target" :companies="targets" />

  <div v-else class="min-h-screen">
    <header class="bg-navy-900 text-white">
      <div class="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <div>
          <p class="text-xs font-medium uppercase tracking-widest text-navy-100/70">
            Skill Gap &amp; Growth Advisor
          </p>
          <h1 class="text-xl font-semibold">{{ target }}</h1>
        </div>
        <button
          type="button"
          class="rounded-lg border border-navy-500 px-4 py-2 text-sm font-medium hover:bg-navy-700"
          @click="target = null"
        >
          Ander bedrijf
        </button>
      </div>
    </header>

    <main class="mx-auto max-w-7xl space-y-10 px-6 py-8">
      <p v-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        {{ error }}
      </p>
      <p v-else-if="loading" class="text-sm text-slate-600">Data laden…</p>
      <p v-else class="text-sm text-slate-600">
        Vergeleken met {{ peerNames.length }} peer-bedrijven over
        {{ timelines.map(timelineLabel).join(' en ') }}.
      </p>

      <section aria-labelledby="advice-heading">
        <h2 id="advice-heading" class="text-lg font-semibold text-navy-900">Strategisch advies</h2>
        <div v-if="advice.length" class="mt-4 grid gap-6 md:grid-cols-2">
          <AdviceCard v-for="item in advice" :key="item.skill" :item="item" />
        </div>
        <p
          v-else-if="!hasTargetData"
          class="mt-4 rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600"
        >
          Er is nog geen vacaturedata van jouw bedrijf in de Slice 3-output, dus er kan geen
          vergelijking worden gemaakt. De peer-tijdlijnen staan hieronder.
        </p>
        <p
          v-else
          class="mt-4 rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600"
        >
          Er zijn geen skills met een kloof van minimaal 10 procentpunt ten opzichte van de peers.
        </p>
      </section>

      <section v-if="hasTargetData" aria-labelledby="market-heading">
        <h2 id="market-heading" class="text-lg font-semibold text-navy-900">
          Marktgemiddelde per skill
        </h2>
        <div class="mt-4">
          <MarketTable :data="data" :target="target" :skills="skills" :timelines="timelines" />
        </div>
      </section>

      <section aria-labelledby="companies-heading">
        <h2 id="companies-heading" class="text-lg font-semibold text-navy-900">
          Skills per bedrijf
        </h2>
        <div class="mt-4 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          <CompanyCard
            v-for="company in [target, ...peerNames]"
            :key="company"
            :name="company"
            :rates="data[company] ?? {}"
            :skills="skills"
            :timelines="timelines"
            :is-target="company === target"
          />
        </div>
      </section>
    </main>
  </div>
</template>
