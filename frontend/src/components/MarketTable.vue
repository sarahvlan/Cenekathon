<script setup lang="ts">
import type { SkillGapData } from '@/types'
import { marketAverage, timelineLabel } from '@/lib/analysis'
import SkillBar from './SkillBar.vue'

const props = defineProps<{
  data: SkillGapData
  target: string
  skills: string[]
  timelines: string[]
}>()

function targetRate(timeline: string, skill: string): number {
  return props.data[props.target]?.[timeline]?.[skill] ?? 0
}

function diffLabel(diff: number): string {
  const pts = Math.round(diff * 100)
  return pts > 0 ? `+${pts} pp` : `${pts} pp`
}
</script>

<template>
  <div class="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
    <div class="flex items-center gap-6 border-b border-slate-200 px-5 py-3 text-xs text-slate-600">
      <span class="flex items-center gap-2">
        <span class="h-2.5 w-2.5 rounded-full bg-navy-700" />
        Jouw bedrijf
      </span>
      <span class="flex items-center gap-2">
        <span class="h-2.5 w-2.5 rounded-full bg-slate-400" />
        Marktgemiddelde
      </span>
    </div>
    <table class="w-full min-w-[640px] border-collapse text-left">
      <thead>
        <tr class="border-b border-slate-200 text-xs uppercase tracking-wider text-slate-500">
          <th class="px-5 py-3 font-medium">Skill</th>
          <th v-for="timeline in timelines" :key="timeline" class="px-5 py-3 font-medium">
            {{ timelineLabel(timeline) }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="skill in skills" :key="skill" class="border-b border-slate-100 last:border-0">
          <td class="w-40 px-5 py-4 text-sm font-medium text-slate-900">{{ skill }}</td>
          <td v-for="timeline in timelines" :key="timeline" class="px-5 py-4">
            <div class="flex items-center gap-4">
              <div class="flex-1 space-y-1.5">
                <SkillBar :value="targetRate(timeline, skill)" />
                <SkillBar :value="marketAverage(data, timeline, skill)" tone="muted" />
              </div>
              <span
                class="w-20 text-right text-sm tabular-nums"
                :class="
                  targetRate(timeline, skill) >= marketAverage(data, timeline, skill)
                    ? 'font-semibold text-navy-900'
                    : 'text-slate-500'
                "
              >
                {{ diffLabel(targetRate(timeline, skill) - marketAverage(data, timeline, skill)) }}
              </span>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <p class="border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
      Marktgemiddelde = gemiddelde over alle bedrijven, inclusief jouw bedrijf. Percentages zijn
      adoptiepercentages van vacatures; pp = procentpunt.
    </p>
  </div>
</template>
