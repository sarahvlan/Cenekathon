<script setup lang="ts">
import type { TimelineRates } from '@/types'
import { timelineLabel } from '@/lib/analysis'
import SkillBar from './SkillBar.vue'

defineProps<{
  name: string
  rates: TimelineRates
  skills: string[]
  timelines: string[]
  isTarget: boolean
}>()
</script>

<template>
  <article
    class="rounded-xl border bg-white p-6 shadow-sm"
    :class="isTarget ? 'border-navy-700 ring-1 ring-navy-700' : 'border-slate-200'"
  >
    <header class="flex items-center justify-between">
      <h3 class="text-base font-semibold text-navy-900">{{ name }}</h3>
      <span
        v-if="isTarget"
        class="rounded-full bg-navy-900 px-2.5 py-0.5 text-xs font-medium text-white"
      >
        Jouw bedrijf
      </span>
    </header>

    <div class="mt-5 space-y-5">
      <section v-for="timeline in timelines" :key="timeline">
        <p class="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">
          {{ timelineLabel(timeline) }}
        </p>
        <ul class="space-y-2.5">
          <li
            v-for="skill in skills"
            :key="skill"
            class="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] items-center gap-4"
          >
            <span class="truncate text-sm text-slate-700">{{ skill }}</span>
            <SkillBar
              :value="rates[timeline]?.[skill] ?? 0"
              :tone="isTarget ? 'primary' : 'muted'"
            />
          </li>
        </ul>
      </section>
    </div>
  </article>
</template>
