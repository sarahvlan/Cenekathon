<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { SkillGapData, SkillGapResponse } from '@/types'
import { allSkills, buildAdvice, sortedTimelines, timelineLabel } from '@/lib/analysis'
import CompanyPicker from '@/components/CompanyPicker.vue'
import AdviceCard from '@/components/AdviceCard.vue'
import MarketTable from '@/components/MarketTable.vue'
import CompanyCard from '@/components/CompanyCard.vue'

interface Slice1Status {
  status: 'idle' | 'running' | 'done' | 'error'
  target?: string
  log?: string
  exitCode?: number | null
}

// Alle bedrijven uit de databank (suggestielijst) en het gekozen doelbedrijf.
const companies = ref<string[]>([])
const companiesError = ref<string | null>(null)
const target = ref<string | null>(null)
const data = ref<SkillGapData>({})
const slice1 = ref<Slice1Status>({ status: 'idle' })
const loading = ref(false)
const error = ref<string | null>(null)
let pollTimer: number | undefined

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  const body = await res.json()
  if (!res.ok) throw new Error(body.error ?? res.statusText)
  return body as T
}

onMounted(async () => {
  try {
    const list = await getJson<{ name: string }[]>('/api/companies')
    companies.value = list.map((c) => c.name)
  } catch (e) {
    companiesError.value = String(e)
  }
})

onBeforeUnmount(() => stopPolling())

// Na de keuze start Slice 1 voor dit bedrijf.
watch(target, async (name) => {
  if (!name) return
  error.value = null
  data.value = {}
  try {
    const res = await fetch('/api/slice1', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: name }),
    })
    const body = await res.json()
    if (!res.ok) throw new Error(body.error ?? res.statusText)
    slice1.value = { status: 'running', target: name }
    startPolling(name)
  } catch (e) {
    error.value = String(e)
  }
})

function startPolling(name: string): void {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      slice1.value = await getJson<Slice1Status>('/api/slice1')
    } catch (e) {
      error.value = String(e)
      stopPolling()
      return
    }
    if (slice1.value.status !== 'running') {
      stopPolling()
      if (slice1.value.status === 'done') await loadSkillGap(name)
    }
  }, 3000)
}

function stopPolling(): void {
  if (pollTimer !== undefined) window.clearInterval(pollTimer)
  pollTimer = undefined
}

// Slice 3-output voor het doelbedrijf. Zonder output (Slice 2 en 3 nog niet gedraaid) blijft het leeg.
async function loadSkillGap(name: string): Promise<void> {
  loading.value = true
  try {
    const res = await getJson<SkillGapResponse>(`/api/skill-gap?target=${encodeURIComponent(name)}`)
    data.value = res.data
  } catch {
    data.value = {}
  } finally {
    loading.value = false
  }
}

function chooseAnother(): void {
  stopPolling()
  target.value = null
  data.value = {}
  slice1.value = { status: 'idle' }
  error.value = null
}

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
  <CompanyPicker
    v-if="!target"
    v-model="target"
    :companies="companies"
    :load-error="companiesError"
  />

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
          @click="chooseAnother"
        >
          Ander bedrijf
        </button>
      </div>
    </header>

    <main class="mx-auto max-w-7xl space-y-10 px-6 py-8">
      <section
        v-if="slice1.status === 'running'"
        class="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-700"
      >
        Slice 1 draait voor <strong>{{ target }}</strong>. Dit kan enkele minuten duren.
      </section>
      <section
        v-else-if="slice1.status === 'error'"
        class="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-800"
      >
        <p>Slice 1 is mislukt (exit {{ slice1.exitCode }}).</p>
        <pre class="mt-3 max-h-60 overflow-auto whitespace-pre-wrap text-xs">{{ slice1.log }}</pre>
      </section>

      <p v-if="error" class="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        {{ error }}
      </p>
      <p v-else-if="loading" class="text-sm text-slate-600">Analyse laden…</p>
      <p v-else-if="slice1.status === 'done' && !hasTargetData" class="text-sm text-slate-600">
        Slice 1 is klaar voor {{ target }}. Er is nog geen analyse-output (Slice 2 en 3). Zodra die
        bestaat, verschijnt de vergelijking hier.
      </p>
      <p v-else-if="hasTargetData" class="text-sm text-slate-600">
        Vergeleken met {{ peerNames.length }} peer-bedrijven over
        {{ timelines.map(timelineLabel).join(' en ') }}.
      </p>

      <template v-if="hasTargetData">
        <section aria-labelledby="advice-heading">
          <h2 id="advice-heading" class="text-lg font-semibold text-navy-900">Strategisch advies</h2>
          <div v-if="advice.length" class="mt-4 grid gap-6 md:grid-cols-2">
            <AdviceCard v-for="item in advice" :key="item.skill" :item="item" />
          </div>
          <p
            v-else
            class="mt-4 rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600"
          >
            Er zijn geen skills met een kloof van minimaal 10 procentpunt ten opzichte van de peers.
          </p>
        </section>

        <section aria-labelledby="market-heading">
          <h2 id="market-heading" class="text-lg font-semibold text-navy-900">
            Marktgemiddelde per skill
          </h2>
          <div class="mt-4">
            <MarketTable :data="data" :target="target" :skills="skills" :timelines="timelines" />
          </div>
        </section>
      </template>

      <section v-if="Object.keys(data).length" aria-labelledby="companies-heading">
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
