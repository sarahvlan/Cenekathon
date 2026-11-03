# SPEC.md - Competitive Skill Gap & Growth Advisor

## 1. Goal
Het doel van deze tool is om de eigen historische vacatures van een financiële instelling te vergelijken met die van succesvolle, groeiende of beursgenoteerde concurrenten (en specifiek de bedrijven die een vergelijkbaar groeipad hebben gevolgd). De output levert concreet advies over welke specifieke skills je moet toevoegen aan je openstaande functies om sneller te groeien dan de concurrentie op jouw niveau.

## 2. Not-Doing List
- GEEN login- of gebruikersbeheersysteem.
- GEEN complexe mobiele UI (een strak en snel web-dashboard volstaat).
- GEEN automatische vacature-aanpassing of tekstverwerker; de focus ligt puur op strategisch advies.

## 3. Architecture & 4-Slice Ownership

- **Slice 1: Data Spine & Company Profiling (Data & Filters)**
  - Eigenaar: [Naam teamlid]
  - Verantwoordelijk voor het inlezen en opschonen van de ruwe Parquet/DuckDB vacaturedata, het normaliseren van bedrijfsnamen, het categoriseren van bedrijfsgrootte en het markeren van 'succesvolle/groeiende' concurrenten.

- **Slice 2: Path Matching Engine (Peer & Trajectory Matcher)**
  - Eigenaar: [Naam teamlid]
  - Verantwoordelijk voor de vergelijkingslogica: bepalen welke rivalen een vergelijkbaar historisch pad hebben doorlopen als het doelbedrijf en het koppelen van historische vacatures van deze relevante peer-groep.

- **Slice 3: Skill Extraction & Gap Analysis (Skill & AI Pipeline)**
  - Eigenaar: [Naam teamlid]
  - Verantwoordelijk voor het extraheren en labelen van specifieke vaardigheden uit de vacatureteksten (bijv. via embeddings/LLM/regex) en het berekenen van de relatieve skill-kloof (adoptiepercentage bij concurrentie vs. doelbedrijf).

- **Slice 4: Advice Generator & Frontend Shell (UI & Insights)**
  - Eigenaar: [Naam teamlid]
  - Verantwoordelijk voor het bouwen van de web-UI/dashboard, het vertalen van de berekende skill-kloven naar concrete, actiegerichte advieskaarten (inclusief headlines en strategische aanbevelingen) voor de eindpresentatie.

---

## 4. Contracts (Source of Truth)

### Contract 1: Input Data Spine (`spine_raw_jobs`)
*Gegenerereerd door Slice 1, gelezen door Slice 2*

```json
{
  "job_id": "string",
  "company_name": "string",
  "company_size_tier": "string",
  "is_successful_growth_peer": true,
  "publication_date": "YYYY-MM-DD",
  "job_title": "string",
  "description_text": "string"
}
```

### Contract 2: Peer-Matched Trajectories (`path_matched_peers`)
*Gegenerereerd door Slice 2, gelezen door Slice 3*

```json
{
  "job_id": "string",
  "company_clean": "string",
  "is_target_company": false,
  "followed_same_path": true,
  "peer_category": "string",
  "job_title": "string",
  "description_text": "string"
}
```

### Contract 3: Skill Gap Metrics (`skill_gap_analysis`)
*Gegenerereerd door Slice 3, gelezen door Slice 4*

```json
{
  "role_category": "string",
  "skill_name": "string",
  "target_company_adoption_rate": 0.10,
  "peer_group_adoption_rate": 0.55,
  "gap_percentage": 0.45
}
```

### Contract 4: Output Card Format (`advice_output_card`)
*Gegenerereerd door Slice 4 voor de UI/Demo*

```json
{
  "slice": "competitive_path_skill_gap",
  "target_company": "Jouw Bank",
  "headline": "Voeg 'AI Governance' toe aan je vacatures om het pad van succesvolle groeiers te volgen",
  "skills_to_add": [
    {
      "skill": "AI Governance",
      "peer_adoption_rate": "55%",
      "target_adoption_rate": "10%"
    }
  ],
  "strategic_advice": "Concurrenten die een vergelijkbaar groeipad volgden, vragen nu in meer dan de helft van deze vacatures om AI Governance. Door dit toe te voegen, versnel je de groei ten opzichte van de markt."
}
```