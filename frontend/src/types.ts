// Contract 3 (skill_gap_analysis) as consumed by the UI, grouped per company.
// Example: { "Bedrijf A": { "1_jaar_na_match": { "AI Governance": 0.25 } } }
// Values are adoption rates between 0 and 1.
export type SkillRates = Record<string, number>
export type TimelineRates = Record<string, SkillRates>
export type SkillGapData = Record<string, TimelineRates>

// Antwoord van GET /api/skill-gap?target=... (zie frontend/vite.config.ts).
export interface SkillGapResponse {
  target: string
  data: SkillGapData
  matchesFile: string | null
}

// Computed advice item for one skill the target company is missing.
export interface AdviceItem {
  skill: string
  targetRate: number
  peerRate: number
  gap: number
  firstTimeline: string
  lastTimeline: string
  gapLater: number
  headline: string
  strategicAdvice: string
}

// Contract 4 (advice_output_card) output format.
export interface AdviceOutputCard {
  slice: 'competitive_path_skill_gap'
  target_company: string
  headline: string
  skills_to_add: {
    skill: string
    peer_adoption_rate: string
    target_adoption_rate: string
  }[]
  strategic_advice: string
}
