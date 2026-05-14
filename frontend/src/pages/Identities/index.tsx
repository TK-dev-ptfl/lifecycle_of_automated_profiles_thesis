import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getProxies, updateProxy } from '../../api/proxies'
import { getEmails, updateEmail } from '../../api/emails'
import { createIdentity, deleteIdentity as deleteIdentityApi } from '../../api/identities'
import { Modal }  from '../../components/ui/Modal'
import { Button } from '../../components/ui/Button'
import { format } from 'date-fns'
import type { EmailAccount, IdentityStatus, Proxy } from '../../types'

// ─── Types ────────────────────────────────────────────────────────────────────

interface HardwareProfile {
  os: string; os_version: string
  browser: string; browser_version: string
  user_agent: string
  screen_width: number; screen_height: number
  color_depth: number; pixel_ratio: number
  device_memory: number; hardware_concurrency: number
  webgl_vendor: string; webgl_renderer: string
  canvas_seed: string
}

interface BehaviorHabits {
  scrolling_speed: 'very_slow' | 'slow' | 'medium' | 'fast' | 'very_fast'
  typing_speed: 'slow' | 'medium' | 'fast'
  speech_patterns: string[]
  topics_of_interest: string[]
  active_hours_start: number
  active_hours_end: number
  session_duration_min: number
  session_duration_max: number
  posts_per_day: number
  like_ratio: number
}

interface ProxySnapshot {
  id: string; host: string; port: number
  country: string; type: string; protocol: string
}

interface RichIdentity {
  id: string
  first_name: string; last_name: string; display_name: string; username: string
  date_of_birth: string; age: number
  country: string; country_code: string; city: string
  languages: string[]; timezone: string; timezone_offset: number
  email: string; email_id: string
  password: string
  proxy_ids: string[]; proxy_details: ProxySnapshot[]
  hardware: HardwareProfile
  habits: BehaviorHabits
  status: IdentityStatus
  created_at: string
}

const IDENTITY_PLATFORM_LABEL = 'Reddit'

// ─── Country data ─────────────────────────────────────────────────────────────

interface CountryDef { name: string; cities: string[]; languages: string[]; timezone: string; tz_offset: number }

const COUNTRIES: Record<string, CountryDef> = {
  SK: { name: 'Slovakia',       cities: ['Bratislava','Košice','Prešov','Žilina','Banská Bystrica','Nitra'],     languages: ['sk','cs','en'], timezone: 'Europe/Bratislava', tz_offset: 1  },
  CZ: { name: 'Czech Republic', cities: ['Prague','Brno','Ostrava','Plzeň','Liberec','Olomouc'],                 languages: ['cs','sk','en'], timezone: 'Europe/Prague',      tz_offset: 1  },
  DE: { name: 'Germany',        cities: ['Berlin','Munich','Hamburg','Frankfurt','Cologne','Stuttgart'],          languages: ['de','en'],      timezone: 'Europe/Berlin',      tz_offset: 1  },
  US: { name: 'United States',  cities: ['New York','Los Angeles','Chicago','Houston','San Francisco','Seattle'], languages: ['en'],           timezone: 'America/New_York',   tz_offset: -5 },
  GB: { name: 'United Kingdom', cities: ['London','Manchester','Birmingham','Leeds','Glasgow','Liverpool'],       languages: ['en'],           timezone: 'Europe/London',      tz_offset: 0  },
  FR: { name: 'France',         cities: ['Paris','Lyon','Marseille','Toulouse','Nice','Bordeaux'],               languages: ['fr','en'],      timezone: 'Europe/Paris',       tz_offset: 1  },
  PL: { name: 'Poland',         cities: ['Warsaw','Kraków','Gdańsk','Wrocław','Poznań','Łódź'],                  languages: ['pl','en'],      timezone: 'Europe/Warsaw',      tz_offset: 1  },
  AT: { name: 'Austria',        cities: ['Vienna','Graz','Linz','Salzburg','Innsbruck'],                         languages: ['de','en'],      timezone: 'Europe/Vienna',      tz_offset: 1  },
  HU: { name: 'Hungary',        cities: ['Budapest','Debrecen','Miskolc','Pécs','Győr'],                         languages: ['hu','en'],      timezone: 'Europe/Budapest',    tz_offset: 1  },
  NL: { name: 'Netherlands',    cities: ['Amsterdam','Rotterdam','The Hague','Utrecht','Eindhoven'],             languages: ['nl','en'],      timezone: 'Europe/Amsterdam',   tz_offset: 1  },
}

// ─── Name pools ───────────────────────────────────────────────────────────────

const NAMES: Record<string, { m: string[]; f: string[]; l: string[] }> = {
  SK: { m: ['Marek','Tomáš','Peter','Lukáš','Michal','Jakub','Martin','Juraj','Pavel','Ján','Róbert','Dávid','Matej','Filip','Rastislav'],
        f: ['Monika','Jana','Petra','Zuzana','Katarína','Lucia','Mária','Veronika','Eva','Miroslava','Ivana','Barbora','Dominika','Alžbeta','Renáta'],
        l: ['Novák','Kováč','Horváth','Varga','Lukáč','Oravec','Blaho','Sedlák','Krajčí','Baláž','Takáč','Šimko','Sloboda','Mináč','Bukovský'] },
  CZ: { m: ['Tomáš','Jan','Jakub','Ondřej','Martin','Lukáš','Petr','David','Marek','Jiří','Michal','Josef','Pavel','Radek','Miroslav'],
        f: ['Tereza','Lucie','Jana','Markéta','Kateřina','Petra','Veronika','Eva','Monika','Hana','Anna','Klára','Lenka','Barbora','Zuzana'],
        l: ['Novák','Svoboda','Novotný','Dvořák','Černý','Procházka','Kučera','Veselý','Horák','Němec','Pokorný','Kratochvíl','Fiala','Blažek','Šimánek'] },
  DE: { m: ['Lukas','Paul','Jonas','Felix','Leon','Maximilian','Finn','Elias','Noah','Julian','Tobias','Lars','Klaus','Hans','Stefan'],
        f: ['Emma','Hannah','Sofia','Anna','Marie','Lea','Lena','Laura','Mia','Julia','Katharina','Lisa','Sandra','Sabrina','Nicole'],
        l: ['Müller','Schmidt','Schneider','Fischer','Weber','Meyer','Wagner','Becker','Schulz','Hoffmann','Koch','Bauer','Richter','Klein','Wolf'] },
  US: { m: ['James','John','Robert','Michael','William','David','Richard','Joseph','Thomas','Charles','Christopher','Daniel','Matthew','Anthony','Mark'],
        f: ['Mary','Patricia','Jennifer','Linda','Barbara','Elizabeth','Susan','Jessica','Sarah','Karen','Lisa','Nancy','Betty','Margaret','Sandra'],
        l: ['Smith','Johnson','Williams','Brown','Jones','Garcia','Miller','Davis','Wilson','Taylor','Anderson','Thomas','Jackson','White','Harris'] },
  GB: { m: ['Oliver','Harry','George','Jack','Noah','Charlie','Jacob','Alfie','Freddie','Oscar','William','Thomas','James','Henry','Archie'],
        f: ['Olivia','Amelia','Isla','Ava','Mia','Isabella','Sophia','Poppy','Emily','Lily','Jessica','Sophie','Grace','Freya','Chloe'],
        l: ['Smith','Jones','Williams','Taylor','Brown','Davies','Evans','Wilson','Thomas','Roberts','Johnson','Lewis','Walker','Robinson','Wood'] },
  FR: { m: ['Gabriel','Léo','Raphaël','Louis','Hugo','Lucas','Mathis','Ethan','Nathan','Tom','Théo','Jules','Maxime','Antoine','Clément'],
        f: ['Emma','Jade','Louise','Alice','Chloé','Inès','Léa','Manon','Sarah','Zoé','Camille','Laura','Lucie','Marie','Anaïs'],
        l: ['Martin','Bernard','Dubois','Thomas','Robert','Richard','Petit','Durand','Leroy','Moreau','Simon','Laurent','Lefebvre','Michel','Garcia'] },
  PL: { m: ['Jakub','Jan','Mateusz','Michał','Kamil','Piotr','Marcin','Tomasz','Łukasz','Krzysztof','Paweł','Wojciech','Adam','Bartosz','Grzegorz'],
        f: ['Julia','Zuzanna','Maja','Aleksandra','Natalia','Zofia','Anna','Wiktoria','Martyna','Karolina','Agnieszka','Monika','Paulina','Marta','Kasia'],
        l: ['Kowalski','Wiśniewski','Wójcik','Kowalczyk','Kamiński','Lewandowski','Zieliński','Szymański','Woźniak','Dąbrowski','Kozłowski','Jankowski','Mazur','Kwiatkowski','Krawczyk'] },
  AT: { m: ['Lukas','Tobias','Florian','Stefan','Andreas','Michael','Thomas','David','Christoph','Martin','Alexander','Dominik','Markus','Klaus','Peter'],
        f: ['Anna','Laura','Sarah','Julia','Lisa','Katharina','Christina','Sabrina','Bianca','Monika','Sandra','Andrea','Karin','Claudia','Martina'],
        l: ['Müller','Gruber','Huber','Bauer','Wagner','Moser','Mayer','Hofer','Leitner','Berger','Fischer','Steiner','Eder','Wimmer','Fuchs'] },
  HU: { m: ['Péter','László','Gábor','Zoltán','Tamás','Attila','István','Balázs','Dávid','Máté','Ádám','Bence','Márton','Milán','Szabolcs'],
        f: ['Anna','Éva','Katalin','Mária','Edit','Zsófia','Nóra','Petra','Veronika','Barbara','Eszter','Réka','Lilla','Krisztina','Klára'],
        l: ['Nagy','Kovács','Tóth','Szabó','Horváth','Varga','Kiss','Molnár','Németh','Farkas','Fekete','Pap','Balogh','Takács','Lukács'] },
  NL: { m: ['Liam','Noah','Daan','Luuk','Lars','Tim','Ruben','Jesse','Finn','Thijs','Pieter','Sander','Bart','Jeroen','Kevin'],
        f: ['Emma','Olivia','Sophie','Julia','Sara','Fleur','Anne','Noor','Lotte','Lisa','Iris','Roos','Amber','Eline','Manon'],
        l: ['de Jong','Jansen','de Vries','van den Berg','van Dijk','Bakker','Janssen','Visser','Smit','Meijer','de Boer','Mulder','Bos','Dekker','Peters'] },
}

// ─── Hardware combos ──────────────────────────────────────────────────────────

const HW_COMBOS = [
  { os: 'Windows', os_v: '10',         browser: 'Chrome',  bvMin: 120, bvMax: 126 },
  { os: 'Windows', os_v: '11',         browser: 'Chrome',  bvMin: 122, bvMax: 126 },
  { os: 'Windows', os_v: '11',         browser: 'Edge',    bvMin: 120, bvMax: 126 },
  { os: 'macOS',   os_v: '14 Sonoma',  browser: 'Chrome',  bvMin: 120, bvMax: 126 },
  { os: 'macOS',   os_v: '14 Sonoma',  browser: 'Safari',  bvMin: 17,  bvMax: 17  },
  { os: 'macOS',   os_v: '13 Ventura', browser: 'Chrome',  bvMin: 118, bvMax: 124 },
  { os: 'Ubuntu',  os_v: '22.04',      browser: 'Firefox', bvMin: 120, bvMax: 126 },
]

const SCREENS: [number, number][] = [
  [1920,1080],[2560,1440],[1366,768],[1440,900],[1280,800],[1680,1050],[1920,1200],
]

const WEBGL: [string, string][] = [
  ['Intel Inc.','Intel(R) UHD Graphics 620'],
  ['Intel Inc.','Intel(R) Iris(R) Xe Graphics'],
  ['NVIDIA Corporation','NVIDIA GeForce RTX 3060/PCIe/SSE2'],
  ['AMD','AMD Radeon RX 6600 XT'],
  ['Apple Inc.','Apple M2'],
  ['Intel Inc.','Intel(R) HD Graphics 4000'],
]

const TOPICS = [
  'technology','gaming','sports','music','movies','cooking','travel','fitness',
  'politics','science','books','photography','finance','nature','history','art',
  'fashion','cars','diy','animals','memes','news','crypto','philosophy',
]
const SPEECH_PATTERNS = [
  'occasional_typo','no_caps','emoji_heavy','abbreviations','double_space',
  'no_punctuation','excessive_ellipsis','all_caps_emphasis',
  'formal_grammar','casual_slang','native_language_mixing',
]

const PW_ADJ  = ['Brave','Swift','Calm','Bold','Dark','Light','Storm','Frost','Stone','Iron','Rapid','Sharp','Clear','Grand']
const PW_NOUN = ['Koala','Tiger','Eagle','Falcon','Wolf','Bear','Fox','Hawk','Lion','Panda','Raven','Shark','Drake','Lynx']
const PW_SPEC = ['!','@','#','$','%','&']

// ─── Utilities ────────────────────────────────────────────────────────────────

function pick<T>(arr: T[]): T { return arr[Math.floor(Math.random() * arr.length)] }
function randInt(min: number, max: number) { return Math.floor(Math.random() * (max - min + 1)) + min }
function pickN<T>(arr: T[], n: number): T[] {
  return [...arr].sort(() => Math.random() - 0.5).slice(0, Math.min(n, arr.length))
}
function normalize(s: string) { return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase() }
function flag(cc: string) {
  return [...cc.toUpperCase()].map(c => String.fromCodePoint(c.charCodeAt(0) + 127397)).join('')
}
function hexSeed(len = 16) {
  return Array.from({ length: len }, () => Math.floor(Math.random() * 16).toString(16)).join('')
}
function genId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0
    const v = c === 'x' ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
}

function genPassword(): string {
  const a = pick(PW_ADJ), n = pick(PW_NOUN), s = pick(PW_SPEC), num = randInt(10, 9999)
  return pick([
    `${a}${n}${s}${num}`,
    `${a}_${n}${num}${s}`,
    `${n}${a}${s}${String(num).padStart(4,'0')}`,
    `${a}${num}${s}${n}`,
  ])
}

// ─── Proxy selection ──────────────────────────────────────────────────────────

function selectProxies(
  requestedCC: string,         // '' = let proxies decide
  freeProxies: Proxy[],
): { cc: string; proxies: Proxy[] } | null {
  if (freeProxies.length === 0) return null

  if (requestedCC === '') {
    // Group by country, prefer countries we have name data for
    const byCC: Record<string, Proxy[]> = {}
    for (const p of freeProxies) {
      const cc = p.country.toUpperCase()
      if (!byCC[cc]) byCC[cc] = []
      byCC[cc].push(p)
    }
    const known = Object.keys(byCC).filter(cc => COUNTRIES[cc])
    const cc = known.length > 0 ? pick(known) : pick(Object.keys(byCC))
    const pool = byCC[cc]
    const count = cc === 'SK'
      ? Math.min(pool.length, randInt(2, 3))
      : Math.min(pool.length, randInt(1, 3))
    return { cc, proxies: pool.slice(0, count) }
  }

  const countryPool = freeProxies.filter(p => p.country.toUpperCase() === requestedCC)

  if (requestedCC === 'SK') {
    if (countryPool.length < 2) return null
    return { cc: 'SK', proxies: countryPool.slice(0, randInt(2, Math.min(countryPool.length, 3))) }
  }

  const pool = countryPool.length > 0 ? countryPool : freeProxies
  return { cc: requestedCC, proxies: pool.slice(0, Math.min(pool.length, randInt(1, 3))) }
}

// ─── Identity generation ──────────────────────────────────────────────────────

function makeUsername(fn: string, ln: string): string {
  const n = normalize(fn), l = normalize(ln)
  const n2 = randInt(10, 99), n4 = randInt(1000, 9999)
  const variants = [`${n}_${l}`, `${n}${n2}`, `${n}_${l}${n2}`, `${n.slice(0,4)}_${l}`, `throwaway_${n}${n4}`]
  return pick(variants).slice(0, 20)
}

function makeDOB(minAge: number, maxAge: number): { dob: string; age: number } {
  const year = new Date().getFullYear() - randInt(minAge, maxAge)
  const month = randInt(1, 12), day = randInt(1, 28)
  const dob = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`
  return { dob, age: Math.floor((Date.now() - new Date(dob).getTime()) / (365.25 * 86400000)) }
}

function buildUA(os: string, browser: string, bv: number): string {
  const win = 'Windows NT 10.0; Win64; x64'
  const mac = 'Macintosh; Intel Mac OS X 10_15_7'
  const wk  = 'AppleWebKit/537.36 (KHTML, like Gecko)'
  const osStr = os === 'Windows' ? win : os === 'macOS' ? mac : 'X11; Ubuntu; Linux x86_64'
  if (browser === 'Chrome')  return `Mozilla/5.0 (${osStr}) ${wk} Chrome/${bv}.0.0.0 Safari/537.36`
  if (browser === 'Edge')    return `Mozilla/5.0 (${osStr}) ${wk} Chrome/${bv}.0.0.0 Safari/537.36 Edg/${bv}.0.0.0`
  if (browser === 'Safari')  return `Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/${bv}.0 Safari/605.1.15`
  return `Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:${bv}.0) Gecko/20100101 Firefox/${bv}.0`
}

function generateIdentityData(cc: string, email: EmailAccount, proxies: Proxy[]): RichIdentity {
  const country = COUNTRIES[cc] ?? COUNTRIES.US
  const names = NAMES[cc] ?? NAMES.US
  const gender = Math.random() > 0.5 ? 'male' : 'female'
  const firstName = pick(gender === 'male' ? names.m : names.f)
  const lastName  = pick(names.l)
  const { dob, age } = makeDOB(18, 48)

  const hw = pick(HW_COMBOS)
  const bv = randInt(hw.bvMin, hw.bvMax)
  const [sw, sh] = pick(SCREENS)
  const [wv, wr] = pick(WEBGL)

  const hardware: HardwareProfile = {
    os: hw.os, os_version: hw.os_v,
    browser: hw.browser, browser_version: String(bv),
    user_agent: buildUA(hw.os, hw.browser, bv),
    screen_width: sw, screen_height: sh,
    color_depth: pick([24, 30, 32]),
    pixel_ratio: pick([1, 1.25, 1.5, 2]),
    device_memory: pick([4, 8, 8, 16]),
    hardware_concurrency: pick([4, 8, 8, 12, 16]),
    webgl_vendor: wv, webgl_renderer: wr,
    canvas_seed: hexSeed(16),
  }

  const habits: BehaviorHabits = {
    scrolling_speed: pick(['very_slow','slow','medium','fast','very_fast']),
    typing_speed: pick(['slow','medium','fast']),
    speech_patterns: pickN(SPEECH_PATTERNS, randInt(2, 4)),
    topics_of_interest: pickN(TOPICS, randInt(3, 7)),
    active_hours_start: randInt(7, 11),
    active_hours_end: randInt(21, 23),
    session_duration_min: randInt(5, 20),
    session_duration_max: randInt(30, 120),
    posts_per_day: randInt(1, 15),
    like_ratio: Math.round(Math.random() * 100) / 100,
  }

  return {
    id: genId(),
    first_name: firstName, last_name: lastName,
    display_name: `${firstName} ${lastName}`,
    username: makeUsername(firstName, lastName),
    date_of_birth: dob, age,
    country: country.name, country_code: cc, city: pick(country.cities),
    languages: country.languages, timezone: country.timezone, timezone_offset: country.tz_offset,
    email: email.address, email_id: email.id,
    password: genPassword(),
    proxy_ids: proxies.map(p => p.id),
    proxy_details: proxies.map(p => ({
      id: p.id, host: p.host, port: p.port,
      country: p.country, type: p.type, protocol: p.protocol,
    })),
    hardware, habits, status: 'fresh',
    created_at: new Date().toISOString(),
  }
}

// ─── localStorage ─────────────────────────────────────────────────────────────

const IDENTITIES_KEY = 'rich_identities'

function loadIdentities(): RichIdentity[] {
  try { return JSON.parse(localStorage.getItem(IDENTITIES_KEY) ?? '[]') } catch { return [] }
}
function saveIdentities(ids: RichIdentity[]) { localStorage.setItem(IDENTITIES_KEY, JSON.stringify(ids)) }


// ─── UI helpers ───────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<IdentityStatus, string> = {
  fresh:   'bg-sky-900/40 text-sky-400 border-sky-700/40',
  active:  'bg-emerald-900/40 text-emerald-400 border-emerald-700/40',
  flagged: 'bg-amber-900/40 text-amber-400 border-amber-700/40',
  burned:  'bg-red-900/40 text-red-400 border-red-700/40',
}

function StatusPill({ status }: { status: IdentityStatus }) {
  return <span className={`px-2 py-0.5 rounded-full border text-xs ${STATUS_STYLES[status]}`}>{status}</span>
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider shrink-0">{title}</h3>
        <div className="flex-1 h-px bg-gray-700/40" />
      </div>
      {children}
    </div>
  )
}

function Field({ label, mono, children }: { label: string; mono?: boolean; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-1.5 border-b border-gray-800/50 last:border-0">
      <span className="text-xs text-gray-600 w-36 shrink-0 mt-0.5 leading-tight">{label}</span>
      <span className={`text-sm text-gray-300 min-w-0 break-all ${mono ? 'font-mono' : ''}`}>{children}</span>
    </div>
  )
}

// ─── Generate Modal ───────────────────────────────────────────────────────────

function GenerateModal({
  proxies, proxiesLoading,
  emailAccounts,
  usedProxyIds, usedEmailIds,
  onGenerate, onClose,
}: {
  proxies: Proxy[]
  proxiesLoading: boolean
  emailAccounts: EmailAccount[]
  usedProxyIds: string[]
  usedEmailIds: string[]
  onGenerate: (country: string) => void | Promise<void>
  onClose: () => void
}) {
  const [country, setCountry]   = useState('')

  // Free proxies: healthy and not already assigned by backend or existing identity
  const freeProxies = proxies.filter(p =>
    p.is_healthy && !p.assigned_bot_id && !usedProxyIds.includes(p.id)
  )

  // Proxy check for chosen country
  const proxyCheck = (() => {
    if (proxiesLoading) return { ok: false, msg: 'Loading proxies…' }
    if (freeProxies.length === 0) return { ok: false, msg: 'No healthy unassigned proxies available. Add proxies in the Proxies page.' }
    if (country === 'SK') {
      const skCount = freeProxies.filter(p => p.country.toUpperCase() === 'SK').length
      if (skCount < 2) return { ok: false, msg: `Slovakia requires 2+ SK proxies — only ${skCount} available.` }
    }
    return { ok: true, msg: '' }
  })()

  // Email check: not in use, not blocked on Reddit
  const emailCheck = (() => {
    const free = emailAccounts.filter(e =>
      !e.used_by_bot_id && !usedEmailIds.includes(e.id) &&
      !e.blocked_on_platforms.includes(IDENTITY_PLATFORM_LABEL)
    )
    if (free.length === 0) return { ok: false, msg: `No free email accounts available for ${IDENTITY_PLATFORM_LABEL}. Add email accounts in the Email Accounts page.` }
    return { ok: true, count: free.length, msg: '' }
  })()

  const canGenerate = proxyCheck.ok && emailCheck.ok

  return (
    <Modal title="Generate Identity" isOpen onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={!canGenerate} onClick={() => onGenerate(country)}>
            Generate
          </Button>
        </div>
      }
    >
      <div className="space-y-5">

        {/* Country */}
        <div>
          <label className="text-xs text-gray-500 block mb-1.5">
            Country <span className="text-gray-700">— leave blank to derive from available proxies</span>
          </label>
          <select value={country} onChange={e => setCountry(e.target.value)}
            className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-300 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value="">Auto (from proxies)</option>
            {Object.entries(COUNTRIES).map(([cc, c]) => (
              <option key={cc} value={cc}>{flag(cc)} {c.name}</option>
            ))}
          </select>
        </div>

        {/* Resource status */}
        <div className="space-y-2">
          {/* Proxy status */}
          <div className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-xs ${
            proxyCheck.ok
              ? 'border-emerald-700/40 bg-emerald-900/10 text-emerald-400'
              : 'border-red-700/40 bg-red-900/10 text-red-400'
          }`}>
            <span className="shrink-0 mt-0.5">{proxyCheck.ok ? '✓' : '✕'}</span>
            <span>
              {proxyCheck.ok
                ? `${freeProxies.length} free prox${freeProxies.length !== 1 ? 'ies' : 'y'} available${country === 'SK' ? ` (${freeProxies.filter(p => p.country.toUpperCase() === 'SK').length} SK)` : ''}`
                : proxyCheck.msg}
            </span>
          </div>

          {/* Email status */}
          <div className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-xs ${
            emailCheck.ok
              ? 'border-emerald-700/40 bg-emerald-900/10 text-emerald-400'
              : 'border-red-700/40 bg-red-900/10 text-red-400'
          }`}>
            <span className="shrink-0 mt-0.5">{emailCheck.ok ? '✓' : '✕'}</span>
            <span>
              {emailCheck.ok
                ? `${emailCheck.count} free email${(emailCheck.count ?? 0) !== 1 ? 's' : ''} available for ${IDENTITY_PLATFORM_LABEL}`
                : emailCheck.msg}
            </span>
          </div>
        </div>

      </div>
    </Modal>
  )
}

// ─── Detail Modal ─────────────────────────────────────────────────────────────

function IdentityDetailModal({ identity: id, onClose }: { identity: RichIdentity; onClose: () => void }) {
  const speedSteps = ['very_slow','slow','medium','fast','very_fast']
  const speedBar = (s: string) => {
    const idx = speedSteps.indexOf(s)
    return '▌'.repeat(idx + 1) + '░'.repeat(4 - idx)
  }
  const tzSign = id.timezone_offset >= 0 ? '+' : ''
  const tzCity = id.timezone.split('/')[1]?.replace(/_/g,' ') ?? id.timezone

  return (
    <Modal title={`${id.display_name} — Full Profile`} isOpen size="xl" onClose={onClose}
      footer={<div className="flex justify-end"><Button variant="ghost" onClick={onClose}>Close</Button></div>}
    >
      <div className="space-y-6">

        <Section title="Personal">
          <div className="grid grid-cols-2 gap-x-8">
            <Field label="Full name">{id.first_name} {id.last_name}</Field>
            <Field label="Username" mono>@{id.username}</Field>
            <Field label="Status"><StatusPill status={id.status} /></Field>
            <Field label="Date of birth">{format(new Date(id.date_of_birth), 'MMMM d, yyyy')}</Field>
            <Field label="Age">{id.age} years old</Field>
            <Field label="Email" mono>{id.email}</Field>
            <Field label="Password" mono>{id.password}</Field>
          </div>
        </Section>

        <Section title="Location & Network">
          <div className="grid grid-cols-2 gap-x-8">
            <Field label="Country">{flag(id.country_code)} {id.country}</Field>
            <Field label="City">{id.city}</Field>
            <Field label="Timezone">{id.timezone} (UTC{tzSign}{id.timezone_offset})</Field>
            <Field label="Languages">
              <div className="flex gap-1 flex-wrap">
                {id.languages.map(l => (
                  <span key={l} className="px-1.5 py-0.5 rounded bg-gray-700/50 text-xs text-gray-300 uppercase">{l}</span>
                ))}
              </div>
            </Field>
          </div>
          {id.proxy_details && id.proxy_details.length > 0 && (
            <div className="mt-3">
              <p className="text-xs text-gray-600 mb-2">Proxies ({id.proxy_details.length})</p>
              <div className="space-y-1.5">
                {id.proxy_details.map(p => (
                  <div key={p.id} className="flex items-center gap-3 rounded-lg bg-gray-800/40 border border-gray-700/40 px-3 py-2">
                    <span className="font-mono text-xs text-gray-200">{p.host}:{p.port}</span>
                    <span className="text-xs text-gray-500">{p.type}</span>
                    <span className="text-xs text-gray-500">{p.protocol.toUpperCase()}</span>
                    <span className="ml-auto text-xs text-gray-500">{flag(p.country.length === 2 ? p.country : 'UN')} {p.country}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Section>

        <Section title="Browser & Hardware">
          <div className="grid grid-cols-2 gap-x-8">
            <Field label="OS">{id.hardware.os} {id.hardware.os_version}</Field>
            <Field label="Browser">{id.hardware.browser} {id.hardware.browser_version}</Field>
            <Field label="Screen">
              {id.hardware.screen_width}×{id.hardware.screen_height} — {id.hardware.color_depth}-bit, DPR {id.hardware.pixel_ratio}
            </Field>
            <Field label="Device memory">{id.hardware.device_memory} GB RAM</Field>
            <Field label="CPU threads">{id.hardware.hardware_concurrency} logical cores</Field>
            <Field label="WebGL vendor">{id.hardware.webgl_vendor}</Field>
            <Field label="WebGL renderer">{id.hardware.webgl_renderer}</Field>
            <Field label="Canvas seed" mono>{id.hardware.canvas_seed}</Field>
          </div>
          <div className="mt-3 rounded-lg bg-gray-950/70 border border-gray-700/40 px-3 py-2.5">
            <p className="text-xs text-gray-600 mb-1">User-Agent</p>
            <p className="font-mono text-xs text-gray-400 break-all leading-relaxed">{id.hardware.user_agent}</p>
          </div>
        </Section>

        <Section title="Behavioral Profile">
          <div className="grid grid-cols-2 gap-x-8">
            <Field label="Scrolling speed">
              <span className="font-mono text-brand-400 mr-2">{speedBar(id.habits.scrolling_speed)}</span>
              <span className="text-gray-500 text-xs">{id.habits.scrolling_speed.replace(/_/g,' ')}</span>
            </Field>
            <Field label="Typing speed">{id.habits.typing_speed}</Field>
            <Field label="Active hours">
              <span className="font-mono">
                {String(id.habits.active_hours_start).padStart(2,'0')}:00 – {String(id.habits.active_hours_end).padStart(2,'0')}:00
              </span>
              <span className="text-gray-600 text-xs ml-1.5">local ({tzCity})</span>
            </Field>
            <Field label="Session">{id.habits.session_duration_min}–{id.habits.session_duration_max} min</Field>
            <Field label="Posts / day">~{id.habits.posts_per_day}</Field>
            <Field label="Like ratio">{Math.round(id.habits.like_ratio * 100)}%</Field>
          </div>
          <div className="mt-4 space-y-3">
            <div>
              <p className="text-xs text-gray-600 mb-1.5">Speech patterns</p>
              <div className="flex gap-1.5 flex-wrap">
                {id.habits.speech_patterns.map(p => (
                  <span key={p} className="px-2 py-0.5 rounded-full bg-gray-800/60 border border-gray-700/40 text-xs text-gray-400">
                    {p.replace(/_/g,' ')}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs text-gray-600 mb-1.5">Topics of interest</p>
              <div className="flex gap-1.5 flex-wrap">
                {id.habits.topics_of_interest.map(t => (
                  <span key={t} className="px-2 py-0.5 rounded-full bg-brand-900/30 border border-brand-700/30 text-xs text-brand-400">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </Section>

      </div>
    </Modal>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function IdentitiesPage() {
  const [identities, setIdentities]       = useState<RichIdentity[]>(loadIdentities)
  const [showGenerate, setShowGenerate]   = useState(false)
  const [preview, setPreview]             = useState<RichIdentity | null>(null)

  const { data: proxies = [], isLoading: proxiesLoading, refetch: refetchProxies } = useQuery({
    queryKey: ['proxies'],
    queryFn: () => getProxies(),
    refetchInterval: 15000,
  })
  const { data: emailAccounts = [], refetch: refetchEmails } = useQuery({
    queryKey: ['emails'],
    queryFn: () => getEmails(),
  })

  // IDs already committed to existing identities
  const usedProxyIds = identities.flatMap(i => i.proxy_ids ?? [])
  const usedEmailIds = identities.map(i => i.email_id).filter(Boolean)

  async function handleGenerate(requestedCountry: string) {
    const freeProxies = proxies.filter(p =>
      p.is_healthy && !p.assigned_bot_id && !usedProxyIds.includes(p.id)
    )

    const proxyResult = selectProxies(requestedCountry, freeProxies)
    if (!proxyResult) return

    const { cc, proxies: chosenProxies } = proxyResult

    const freeEmails = emailAccounts.filter(e =>
      !e.used_by_bot_id &&
      !usedEmailIds.includes(e.id) &&
      !e.blocked_on_platforms.includes(IDENTITY_PLATFORM_LABEL)
    )
    if (freeEmails.length === 0) return

    const chosenEmail = pick(freeEmails)

    const draftIdentity = generateIdentityData(cc, chosenEmail, chosenProxies)

    // Persist identity in backend DB first.
    const created = await createIdentity({
      display_name: draftIdentity.display_name,
      username: draftIdentity.username,
      email: draftIdentity.email,
      email_provider: draftIdentity.email.split('@')[1] ?? 'unknown',
      email_password: null,
      phone_number: null,
      phone_provider: null,
      profile_photo_url: null,
      bio: null,
      location: draftIdentity.country_code,
      age: draftIdentity.age,
      interests: draftIdentity.habits.topics_of_interest,
      browser_profile_id: `bp_${draftIdentity.id.slice(0, 8)}`,
      browser_profile_provider: 'custom',
      password: draftIdentity.password,
    })
    const identity: RichIdentity = {
      ...draftIdentity,
      id: created.id,
      created_at: created.created_at,
    }

    // Mark proxies as in use by this identity
    await Promise.all(chosenProxies.map((p) => updateProxy(p.id, { assigned_bot_id: identity.id })))
    await refetchProxies()

    // Mark email as in use
    await updateEmail(chosenEmail.id, { used_by_bot_id: identity.id })
    await refetchEmails()

    const updatedIdentities = [identity, ...identities]
    setIdentities(updatedIdentities)
    saveIdentities(updatedIdentities)
    setShowGenerate(false)
  }

  async function deleteIdentity(id: string) {
    const identity = identities.find(i => i.id === id)

    // Free proxies assigned to this identity
    if (identity?.proxy_ids?.length) {
      await Promise.all(identity.proxy_ids.map((proxyId) => updateProxy(proxyId, { assigned_bot_id: null })))
      await refetchProxies()
    }

    // Free email if it was assigned to this identity
    if (identity?.email_id) {
      const assignedEmail = emailAccounts.find(e => e.id === identity.email_id && e.used_by_bot_id === id)
      if (assignedEmail) {
        await updateEmail(assignedEmail.id, { used_by_bot_id: null })
        await refetchEmails()
      }
    }

    // Remove identity from backend DB.
    await deleteIdentityApi(id)

    const updated = identities.filter(i => i.id !== id)
    setIdentities(updated)
    saveIdentities(updated)
  }

  const stats = [
    { label: 'Total',   value: identities.length,                              cls: 'text-gray-200' },
    { label: 'Fresh',   value: identities.filter(i => i.status==='fresh').length,    cls: 'text-sky-400' },
    { label: 'Active',  value: identities.filter(i => i.status==='active').length,   cls: 'text-emerald-400' },
    { label: 'Flagged', value: identities.filter(i => i.status==='flagged').length,  cls: 'text-amber-400' },
    { label: 'Burned',  value: identities.filter(i => i.status==='burned').length,   cls: 'text-red-400' },
  ]

  return (
    <div className="space-y-5">

      <div className="grid grid-cols-5 gap-4">
        {stats.map(s => (
          <div key={s.label} className="rounded-xl border border-gray-700/60 bg-gray-800/40 px-5 py-4">
            <p className={`text-2xl font-bold tabular-nums ${s.cls}`}>{s.value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-gray-700/60 bg-gray-900 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700/50">
          <h2 className="text-sm font-semibold text-gray-200">Identities</h2>
          <Button onClick={() => setShowGenerate(true)}>⚡ Generate Identity</Button>
        </div>

        {identities.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-gray-600 text-sm">No identities yet</p>
            <p className="text-xs text-gray-700 mt-1">Click "Generate Identity" to create one.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700/50">
                  {['Identity','Email & Proxies','Location','Age','Browser','Status',''].map(h => (
                    <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {identities.map(id => {
                  return (
                    <tr key={id.id} className="border-b border-gray-800/60 hover:bg-gray-800/20 transition-colors last:border-0">

                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-100 whitespace-nowrap">{id.display_name}</p>
                        <p className="text-xs text-gray-500 font-mono">@{id.username}</p>
                      </td>

                      <td className="px-4 py-3 max-w-[280px]">
                        <p className="font-mono text-xs text-gray-300 truncate">{id.email || '—'}</p>
                        {(id.proxy_details?.length ?? 0) > 0 ? (
                          <div className="mt-1.5 space-y-1">
                            {id.proxy_details.slice(0, 2).map((p) => (
                              <p key={p.id} className="font-mono text-[11px] text-gray-500 truncate">
                                {p.host}:{p.port}
                              </p>
                            ))}
                            {id.proxy_details.length > 2 && (
                              <p className="text-[11px] text-gray-600">
                                +{id.proxy_details.length - 2} more
                              </p>
                            )}
                          </div>
                        ) : (
                          <p className="text-xs text-gray-600">no proxies</p>
                        )}
                      </td>

                      <td className="px-4 py-3">
                        <p className="text-gray-300 whitespace-nowrap">{flag(id.country_code)} {id.country}</p>
                        <p className="text-xs text-gray-600">{id.city}</p>
                      </td>

                      <td className="px-4 py-3 text-gray-400">{id.age}</td>

                      <td className="px-4 py-3">
                        <p className="text-gray-300 whitespace-nowrap">{id.hardware.browser} {id.hardware.browser_version}</p>
                        <p className="text-xs text-gray-600">{id.hardware.os} {id.hardware.os_version}</p>
                      </td>

                      <td className="px-4 py-3"><StatusPill status={id.status} /></td>

                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <button onClick={() => setPreview(id)}
                            className="text-xs text-gray-500 hover:text-brand-400 transition-colors whitespace-nowrap">
                            Show more
                          </button>
                          <button onClick={() => deleteIdentity(id.id)}
                            className="text-gray-700 hover:text-red-400 transition-colors text-sm">
                            ✕
                          </button>
                        </div>
                      </td>

                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showGenerate && (
        <GenerateModal
          proxies={proxies}
          proxiesLoading={proxiesLoading}
          emailAccounts={emailAccounts}
          usedProxyIds={usedProxyIds}
          usedEmailIds={usedEmailIds}
          onGenerate={handleGenerate}
          onClose={() => setShowGenerate(false)}
        />
      )}
      {preview && (
        <IdentityDetailModal identity={preview} onClose={() => setPreview(null)} />
      )}
    </div>
  )
}



