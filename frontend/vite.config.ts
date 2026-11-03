import { fileURLToPath, URL } from 'node:url'
import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'

import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// Repo-root en de plekken waar de backend-onderdelen hun output zetten.
const REPO = fileURLToPath(new URL('..', import.meta.url))
const OUTPUT_DIR = join(REPO, 'backend', 'output')
const PYTHON = existsSync(join(REPO, '.venv', 'bin', 'python'))
  ? join(REPO, '.venv', 'bin', 'python')
  : 'python3'

interface SkillTijdlijnFile {
  meta?: { target_company?: string | null; matches_file?: string | null }
  [company: string]: unknown
}

interface Slice1Run {
  target: string
  status: 'running' | 'done' | 'error'
  log: string
  exitCode: number | null
  startedAt: string
}

// Eén Slice 1-run tegelijk; de status blijft in het geheugen van de dev-server.
let slice1Run: Slice1Run | null = null
let slice1Process: ChildProcess | null = null
let companiesCache: { name: string; n_vacancies: number }[] | null = null

function loadOutputs(): { target: string; payload: SkillTijdlijnFile }[] {
  if (!existsSync(OUTPUT_DIR)) return []
  return readdirSync(OUTPUT_DIR)
    .filter((f) => f.startsWith('skill_tijdlijn_') && f.endsWith('.json'))
    .flatMap((file) => {
      const payload = JSON.parse(readFileSync(join(OUTPUT_DIR, file), 'utf-8')) as SkillTijdlijnFile
      const target = payload.meta?.target_company
      return target ? [{ target, payload }] : []
    })
    .sort((a, b) => a.target.localeCompare(b.target, 'nl'))
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.statusCode = status
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify(body))
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = ''
    req.on('data', (chunk: Buffer) => (data += chunk.toString('utf-8')))
    req.on('end', () => resolve(data))
    req.on('error', reject)
  })
}

// Alle bedrijfsnamen uit de ruwe vacatures, voor de suggestielijst.
function loadCompanies(): Promise<{ name: string; n_vacancies: number }[]> {
  if (companiesCache) return Promise.resolve(companiesCache)
  return new Promise((resolve, reject) => {
    const proc = spawn(PYTHON, [join(REPO, 'backend', 'api', 'list_companies.py')], { cwd: REPO })
    let out = ''
    let err = ''
    proc.stdout.on('data', (c: Buffer) => (out += c.toString('utf-8')))
    proc.stderr.on('data', (c: Buffer) => (err += c.toString('utf-8')))
    proc.on('error', reject)
    proc.on('close', (code) => {
      if (code !== 0) return reject(new Error(err.trim() || `list_companies.py exit ${code}`))
      companiesCache = JSON.parse(out) as { name: string; n_vacancies: number }[]
      resolve(companiesCache)
    })
  })
}

// Start slice1_pipeline.py voor het doelbedrijf. Het bedrijf gaat als argument mee, niet via de shell.
function startSlice1(target: string): void {
  const startedAt = new Date().toISOString()
  slice1Run = { target, status: 'running', log: '', exitCode: null, startedAt }
  // --target=<naam> als één argument, zodat een naam met een streepje niet als optie gelezen wordt.
  const proc = spawn(PYTHON, [join(REPO, 'slice1_pipeline.py'), `--target=${target}`], { cwd: REPO })
  slice1Process = proc
  const append = (chunk: Buffer) => {
    if (slice1Run) slice1Run.log = (slice1Run.log + chunk.toString('utf-8')).slice(-8000)
  }
  proc.stdout.on('data', append)
  proc.stderr.on('data', append)
  proc.on('error', (e) => {
    if (slice1Run) {
      slice1Run.status = 'error'
      slice1Run.log += `\n${e.message}`
    }
  })
  proc.on('close', (code) => {
    if (slice1Run) {
      slice1Run.exitCode = code
      slice1Run.status = code === 0 ? 'done' : 'error'
    }
    slice1Process = null
  })
}

// Dev-koppeling tussen UI en de backend-onderdelen. Voor productie vervangt een echte
// backend deze routes.
function backendApi(): Plugin {
  return {
    name: 'backend-api',
    configureServer(server) {
      // GET /api/companies -> [{ name, n_vacancies }]
      server.middlewares.use('/api/companies', (_req: IncomingMessage, res: ServerResponse) => {
        loadCompanies()
          .then((companies) => sendJson(res, 200, companies))
          .catch((e: Error) => sendJson(res, 500, { error: e.message }))
      })

      // GET /api/targets -> ["Doelbedrijf A", ...] (bedrijven met een Slice 3-output)
      server.middlewares.use('/api/targets', (_req: IncomingMessage, res: ServerResponse) => {
        sendJson(res, 200, loadOutputs().map((o) => o.target))
      })

      // GET  /api/slice1 -> status van de laatste run
      // POST /api/slice1 body {"target": "Naam"} -> start Slice 1 voor dit bedrijf
      server.middlewares.use('/api/slice1', (req: IncomingMessage, res: ServerResponse) => {
        if (req.method === 'GET') {
          sendJson(res, 200, slice1Run ?? { status: 'idle' })
          return
        }
        if (req.method !== 'POST') {
          sendJson(res, 405, { error: 'Alleen GET of POST' })
          return
        }
        readBody(req)
          .then((raw) => {
            const target = (JSON.parse(raw || '{}') as { target?: unknown }).target
            if (typeof target !== 'string' || !target.trim()) {
              sendJson(res, 400, { error: 'Geef een bedrijfsnaam op' })
              return
            }
            if (slice1Process) {
              sendJson(res, 409, { error: 'Slice 1 draait al voor een ander bedrijf' })
              return
            }
            startSlice1(target.trim())
            sendJson(res, 202, slice1Run)
          })
          .catch(() => sendJson(res, 400, { error: 'Ongeldige aanvraag' }))
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
          matchesFile: meta?.matches_file ?? null,
        })
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss(), backendApi()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
