<script setup lang="ts">
import type { AdviceItem } from '@/types'
import { formatPercent } from '@/lib/analysis'
import SkillBar from './SkillBar.vue'

defineProps<{ item: AdviceItem }>()
</script>

<template>
  <article class="flex flex-col rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
    <h3 class="text-lg font-semibold leading-snug text-navy-900">{{ item.headline }}</h3>

    <div class="mt-5">
      <div class="flex items-baseline justify-between">
        <p class="text-xs font-medium uppercase tracking-wider text-slate-500">Skill to add</p>
        <span class="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
          +{{ Math.round(item.gap * 100) }} pp
        </span>
      </div>
      <p class="mt-1 text-base font-semibold text-slate-900">{{ item.skill }}</p>

      <div class="mt-3 space-y-2">
        <div>
          <p class="mb-1 text-xs text-slate-500">Peer-gemiddelde</p>
          <SkillBar :value="item.peerRate" tone="muted" />
        </div>
        <div>
          <p class="mb-1 text-xs text-slate-500">Jouw bedrijf</p>
          <SkillBar :value="item.targetRate" />
        </div>
      </div>
    </div>

    <p class="mt-5 border-t border-slate-100 pt-4 text-sm leading-relaxed text-slate-600">
      {{ item.strategicAdvice }}
    </p>
    <p class="sr-only">
      Peer-gemiddelde {{ formatPercent(item.peerRate) }}, jouw bedrijf
      {{ formatPercent(item.targetRate) }}.
    </p>
  </article>
</template>
