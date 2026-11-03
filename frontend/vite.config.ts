import { fileURLToPath, URL } from 'node:url'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'

import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// Slice 3 schrijft per doelbedrijf skill_tijdlijn_<doelbedrijf>.json naar backend/output.
const OUTPUT_DIR = fileURLToPath(new URL('../backend/output', import.meta.url))

interface SkillTijdlijnFile {
  meta?: { target_company?: string | null }
  [company: string]: unknown
}

function loadOutputs(): { target: string; file: string; payload: SkillTijdlijnFile }[] {
  if (!existsSync(OUTPUT_DIR)) return []
  return readdirSync(OUTPUT_DIR)
    .filter((f) => f.startsWith('skill_tijdlijn_') && f.endsWith('.json'))
    .flatMap((file) => {
      const payload = JSON.parse(readFileSync(join(OUTPUT_DIR, file), 'utf-8')) as SkillTijdlijnFile
      const target = payload.meta?.target_company
      return target ? [{ target, file, payload }] : []
    })
    .sort((a, b) => a.target.localeCompare(b.target, 'nl'))
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.statusCode = status
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify(body))
}

// Dev-koppeling tussen UI en Slice 3: geen extra server nodig.
// Voor productie vervangt een echte backend deze twee routes.
function skillGapApi(): Plugin {
  return {
    name: 'skill-gap-api',
    configureServer(server) {
      // GET /api/targets -> ["Doelbedrijf A", ...]
      server.middlewares.use('/api/targets', (_req: IncomingMessage, res: ServerResponse) => {
        sendJson(res, 200, loadOutputs().map((o) => o.target))
      })

      // GET /api/skill-gap?target=Doelbedrijf -> { target, data, matchesFile }
      // data heeft het formaat van Contract 3 per bedrijf, zonder de meta-sleutel.
      server.middlewares.use('/api/skill-gap', (req: IncomingMessage, res: ServerResponse) => {
        const target = new URL(req.url ?? '', 'http://localhost').searchParams.get('target')
        const found = loadOutputs().find((o) => o.target === target)
        if (!found) {
          sendJson(res, 404, { error: `Geen Slice 3-output voor '${target}'` })
          return
        }
        const { meta, ...data } = found.payload
        sendJson(res, 200, {
          target,
          data,
          matchesFile: (meta as { matches_file?: string } | undefined)?.matches_file ?? null,
        })
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss(), skillGapApi()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
