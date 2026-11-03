import type { SkillGapData } from '@/types'

// Voorbeelddata (fictieve bedrijven) met dezelfde structuur als Contract 3.
// Vervang door de output van Slice 3 zodra die beschikbaar is.
export const sampleSkillGap: SkillGapData = {
  'Jouw Bank': {
    '1_jaar_na_match': { 'AI Governance': 0.1, Python: 0.45, 'Cloud Security': 0.3, SQL: 0.5 },
    '2_jaar_na_match': { 'AI Governance': 0.18, Python: 0.52, 'Cloud Security': 0.36, SQL: 0.55 },
  },
  Nordbank: {
    '1_jaar_na_match': { 'AI Governance': 0.55, Python: 0.62, 'Cloud Security': 0.4, SQL: 0.48 },
    '2_jaar_na_match': { 'AI Governance': 0.7, Python: 0.68, 'Cloud Security': 0.45, SQL: 0.5 },
  },
  'Helix Financial': {
    '1_jaar_na_match': { 'AI Governance': 0.25, Python: 0.6, 'Cloud Security': 0.35, SQL: 0.4 },
    '2_jaar_na_match': { 'AI Governance': 0.45, Python: 0.7, 'Cloud Security': 0.42, SQL: 0.44 },
  },
  'Vesta Credit': {
    '1_jaar_na_match': { 'AI Governance': 0.2, Python: 0.5, 'Cloud Security': 0.28, SQL: 0.52 },
    '2_jaar_na_match': { 'AI Governance': 0.35, Python: 0.58, 'Cloud Security': 0.33, SQL: 0.55 },
  },
  'Delta Trust': {
    '1_jaar_na_match': { 'AI Governance': 0.4, Python: 0.58, 'Cloud Security': 0.44, SQL: 0.46 },
    '2_jaar_na_match': { 'AI Governance': 0.52, Python: 0.66, 'Cloud Security': 0.5, SQL: 0.49 },
  },
}
