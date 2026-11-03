<script setup lang="ts">
import { computed } from 'vue'
import { formatPercent } from '@/lib/analysis'

const props = withDefaults(
  defineProps<{
    value: number
    tone?: 'primary' | 'muted'
  }>(),
  { tone: 'primary' },
)

const width = computed(() => `${Math.min(Math.max(props.value, 0), 1) * 100}%`)
const fillClass = computed(() => (props.tone === 'primary' ? 'bg-navy-700' : 'bg-slate-400'))
</script>

<template>
  <div class="flex items-center gap-3">
    <div
      class="h-2 flex-1 overflow-hidden rounded-full bg-slate-200"
      role="img"
      :aria-label="formatPercent(value)"
    >
      <div class="h-full rounded-full" :class="fillClass" :style="{ width }" />
    </div>
    <span class="w-10 text-right text-sm font-medium tabular-nums text-slate-700">
      {{ formatPercent(value) }}
    </span>
  </div>
</template>
