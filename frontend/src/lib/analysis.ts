import type { AdviceItem, AdviceOutputCard, SkillGapData } from '@/types'

// Minimale kloof (in adoptiepercentage-punten, 0-1) voordat een skill als advies verschijnt.
export const GAP_THRESHOLD = 0.1

// "1_jaar_na_match" -> "1 jaar na match"
export function timelineLabel(timeline: string): string {
  return timeline.replace(/_/g, ' ')
}

export function formatPercent(rate: number): string {
  return `${Math.round(rate * 100)}%`
}

export function sortedTimelines(data: SkillGapData): string[] {
  const timelines = new Set<string>()
  for (const company of Object.values(data)) {
    for (const timeline of Object.keys(company)) timelines.add(timeline)
  }
  const years = (t: string) => parseInt(t, 10) || 0
  return [...timelines].sort((a, b) => years(a) - years(b))
}

export function allSkills(data: SkillGapData): string[] {
  const skills = new Set<string>()
  for (const company of Object.values(data)) {
    for (const rates of Object.values(company)) {
      for (const skill of Object.keys(rates)) skills.add(skill)
    }
  }
  return [...skills].sort((a, b) => a.localeCompare(b, 'nl'))
}

// Gemiddelde over de bedrijven die de skill rapporteren. Geen data -> 0.
export function averageRate(
  data: SkillGapData,
  companies: string[],
  timeline: string,
  skill: string,
): number {
  const values = companies
    .map((company) => data[company]?.[timeline]?.[skill])
    .filter((value): value is number => value !== undefined)
  if (values.length === 0) return 0
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

// Marktgemiddelde over alle bedrijven samen (inclusief het doelbedrijf).
export function marketAverage(data: SkillGapData, timeline: string, skill: string): number {
  return averageRate(data, Object.keys(data), timeline, skill)
}

// Peer-gemiddelde: alle bedrijven behalve het doelbedrijf.
export function peerAverage(
  data: SkillGapData,
  target: string,
  timeline: string,
  skill: string,
): number {
  return averageRate(
    data,
    Object.keys(data).filter((company) => company !== target),
    timeline,
    skill,
  )
}

// Adviesitems voor het doelbedrijf, gesorteerd op grootste kloof op de eerste tijdlijn.
export function buildAdvice(data: SkillGapData, target: string): AdviceItem[] {
  const timelines = sortedTimelines(data)
  const first = timelines[0]
  const last = timelines[timelines.length - 1]
  if (first === undefined || last === undefined) return []

  return allSkills(data)
    .map((skill): AdviceItem => {
      const targetRate = data[target]?.[first]?.[skill] ?? 0
      const peerRate = peerAverage(data, target, first, skill)
      const gap = peerRate - targetRate
      const targetLater = data[target]?.[last]?.[skill] ?? 0
      const gapLater = peerAverage(data, target, last, skill) - targetLater
      return {
        skill,
        targetRate,
        peerRate,
        gap,
        firstTimeline: first,
        lastTimeline: last,
        gapLater,
        headline: `Voeg '${skill}' toe aan je vacatures om het pad van succesvolle groeiers te volgen`,
        strategicAdvice: strategicText(skill, targetRate, peerRate, gap, first, last, gapLater),
      }
    })
    .filter((item) => item.gap >= GAP_THRESHOLD)
    .sort((a, b) => b.gap - a.gap)
}

function strategicText(
  skill: string,
  targetRate: number,
  peerRate: number,
  gap: number,
  first: string,
  last: string,
  gapLater: number,
): string {
  const base =
    `Peers die een vergelijkbaar groeipad volgden, vragen binnen ${timelineLabel(first)} in ` +
    `gemiddeld ${formatPercent(peerRate)} van hun vacatures om ${skill}; bij jou is dat ` +
    `${formatPercent(targetRate)}. De kloof bedraagt ${Math.round(gap * 100)} procentpunt.`
  const later =
    first === last
      ? ''
      : ` Binnen ${timelineLabel(last)} blijft de kloof ${Math.round(gapLater * 100)} procentpunt.`
  return `${base}${later} Door ${skill} toe te voegen sluit je aan bij het pad van de groeiers.`
}

export function toOutputCard(data: SkillGapData, target: string): AdviceOutputCard[] {
  return buildAdvice(data, target).map((item) => ({
    slice: 'competitive_path_skill_gap',
    target_company: target,
    headline: item.headline,
    skills_to_add: [
      {
        skill: item.skill,
        peer_adoption_rate: formatPercent(item.peerRate),
        target_adoption_rate: formatPercent(item.targetRate),
      },
    ],
    strategic_advice: item.strategicAdvice,
  }))
}
