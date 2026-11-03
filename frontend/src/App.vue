<script setup lang="ts">
import { computed, ref } from 'vue'
import { sampleSkillGap } from '@/data/sampleSkillGap'
import { allSkills, buildAdvice, sortedTimelines, timelineLabel } from '@/lib/analysis'
import CompanyPicker from '@/components/CompanyPicker.vue'
import AdviceCard from '@/components/AdviceCard.vue'
import MarketTable from '@/components/MarketTable.vue'
import CompanyCard from '@/components/CompanyCard.vue'

// Vervang door een fetch naar de Slice 3-output zodra die beschikbaar is.
const data = sampleSkillGap
const companies = Object.keys(data)

const target = ref<string | null>(null)

const timelines = computed(() => sortedTimelines(data))
const skills = computed(() => allSkills(data))
const advice = computed(() => (target.value ? buildAdvice(data, target.value) : []))
const peerNames = computed(() => companies.filter((c) => c !== target.value))
</script>

<template>
  <CompanyPicker v-if="!target" v-model="target" :companies="companies" />

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
      <p class="text-sm text-slate-600">
        Vergeleken met {{ peerNames.length }} peer-bedrijven over
        {{ timelines.map(timelineLabel).join(' en ') }}.
      </p>

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
