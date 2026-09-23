import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getProxies, updateProxy, testProxy } from '../../api/proxies'
import { getEmails, getEmailPlatforms, updateEmail } from '../../api/emails'
import { createIdentity, deleteIdentity as deleteIdentityApi, getIdentities } from '../../api/identities'
import { Modal }  from '../../components/ui/Modal'
import { Button } from '../../components/ui/Button'
import { format } from 'date-fns'
import type { EmailAccount, EmailPlatform, Identity, IdentityStatus, Proxy } from '../../types'

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

function seedFromString(input: string): number {
  let h = 2166136261
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return Math.abs(h >>> 0)
}

// ─── Proxy selection ──────────────────────────────────────────────────────────

// Picks which country flavors the *identity's own* generated data (name,
// language, timezone, etc. - see generateIdentityData) - purely cosmetic,
// and deliberately decoupled from which physical proxy actually gets used
// (see selectAndVerifyProxies below): the exit IP a proxy happens to sit in
// doesn't need to match the persona's stated country, and requiring that
// match was only ever making proxy selection slower and more likely to fail
// for no real benefit.
function pickIdentityCountry(requestedCC: string, freeProxies: Proxy[]): string {
  if (requestedCC) return requestedCC
  const seen = Array.from(new Set(freeProxies.map(p => p.country.toUpperCase())))
  const known = seen.filter(cc => COUNTRIES[cc])
  if (known.length > 0) return pick(known)
  if (seen.length > 0) return pick(seen)
  return pick(Object.keys(COUNTRIES))
}

// Freshest health data first - a proxy's actual liveness can change within
// minutes (especially for the free/public sources this pool draws from), so
// a proxy checked 5 minutes ago is far more likely to still be accurate than
// one checked 2 days ago. Trying candidates in this order instead of
// whatever arbitrary order the API returned them in means the still-good
// ones get used before stale, probably-dead ones waste a real test call.
function byMostRecentlyChecked(proxies: Proxy[]): Proxy[] {
  return [...proxies].sort((a, b) => b.last_checked.localeCompare(a.last_checked))
}

// Live-tests candidates one at a time via the same "Test" endpoint the
// Proxies page's own Test button uses, instead of trusting the possibly
// stale is_healthy flag cached from the last periodic check - a proxy can
// die between checks, and assigning a dead one to an identity would only
// surface as a failure much later when the signup pipeline actually runs.
// Any residential/mobile proxy in the list is fair game, regardless of
// country - see pickIdentityCountry above for why country doesn't factor in
// here. Stops at the very first candidate that tests alive - one proxy is
// all a single identity ever needs (see identity_service._select_and_test_proxy
// backend-side, which only ever consumes one anyway), so there's no reason
// to keep testing once that's found; the caller can immediately create the
// identity and start its pipeline. Returns null only once the entire list
// has been tried and nothing came back alive.
//
// claimedProxyIds is shared across all identities in a batch generation (see
// generateIdentitiesBatch) - when several identities are generated at once,
// their selectAndVerifyProxies calls run concurrently, and without this
// they could both test-and-pick the exact same proxy (the testProxy() calls
// alone don't reserve anything). A candidate is skipped once claimed, and
// claimed the instant it's confirmed alive - synchronously, before any other
// await - so a sibling task that was testing the same candidate in parallel
// sees it taken by the time its own test resolves and backs off instead of
// double-claiming it. Defaults to a fresh Set for the single-identity case.
async function selectAndVerifyProxies(
  freeProxies: Proxy[],
  onProgress?: (msg: string) => void,
  claimedProxyIds: Set<string> = new Set(),
): Promise<Proxy | null> {
  const candidates = byMostRecentlyChecked(freeProxies)
  const tried = new Set<string>()

  onProgress?.(`Testing ${candidates.length} proxy candidate${candidates.length !== 1 ? 's' : ''}…`)
  for (const candidate of candidates) {
    if (tried.has(candidate.id) || claimedProxyIds.has(candidate.id)) continue
    tried.add(candidate.id)
    try {
      const tested = await testProxy(candidate.id)
      if (tested.is_healthy && !claimedProxyIds.has(candidate.id)) {
        claimedProxyIds.add(candidate.id)
        onProgress?.(`Found a live proxy after checking ${tried.size}`)
        return tested
      }
    } catch {
      // Test request itself failed (network error, proxy timed out hard
      // enough to error rather than just report unhealthy) - treat the
      // same as a failed test and move on to the next candidate.
    }
    onProgress?.(`Checked ${tried.size} prox${tried.size !== 1 ? 'ies' : 'y'} — none alive yet…`)
  }

  return null
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

function generateIdentityData(cc: string, proxies: Proxy[]): RichIdentity {
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
    // No email yet - the Tuta signup pipeline attaches one in the background
    // right after the identity is persisted (see handleGenerate below).
    email: '', email_id: '',
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

function hydrateIdentity(dbIdentity: Identity, proxies: Proxy[], emailAccounts: EmailAccount[]): RichIdentity {
  const cc = (dbIdentity.location || 'US').toUpperCase()
  const country = COUNTRIES[cc] ?? COUNTRIES.US
  const [firstName = dbIdentity.display_name, ...rest] = dbIdentity.display_name.split(' ')
  const lastName = rest.join(' ') || 'Unknown'
  const seed = seedFromString(`${dbIdentity.id}:${dbIdentity.username}:${dbIdentity.email}`)
  const hw = HW_COMBOS[seed % HW_COMBOS.length]
  const bv = hw.bvMin + (seed % (hw.bvMax - hw.bvMin + 1))
  const [sw, sh] = SCREENS[seed % SCREENS.length]
  const [wv, wr] = WEBGL[seed % WEBGL.length]
  const browser = hw.browser
  const browserVersion = String(bv)
  const userAgent = buildUA(hw.os, hw.browser, bv)
  const attachedProxies = proxies.filter((p) => p.assigned_bot_id === dbIdentity.id)
  const linkedEmail = emailAccounts.find((e) => e.address === dbIdentity.email)

  return {
    id: dbIdentity.id,
    first_name: firstName,
    last_name: lastName,
    display_name: dbIdentity.display_name,
    username: dbIdentity.username,
    date_of_birth: `${new Date().getFullYear() - dbIdentity.age}-01-01`,
    age: dbIdentity.age,
    country: country.name,
    country_code: cc,
    city: country.cities[0] ?? 'Unknown',
    languages: country.languages,
    timezone: country.timezone,
    timezone_offset: country.tz_offset,
    email: dbIdentity.email ?? '',
    email_id: linkedEmail?.id ?? '',
    password: '••••••••',
    proxy_ids: attachedProxies.map((p) => p.id),
    proxy_details: attachedProxies.map((p) => ({
      id: p.id, host: p.host, port: p.port, country: p.country, type: p.type, protocol: p.protocol,
    })),
    hardware: {
      os: hw.os,
      os_version: hw.os_v,
      browser,
      browser_version: browserVersion,
      user_agent: userAgent,
      screen_width: sw,
      screen_height: sh,
      color_depth: 24,
      pixel_ratio: 1,
      device_memory: 8,
      hardware_concurrency: 8,
      webgl_vendor: wv,
      webgl_renderer: wr,
      canvas_seed: hexSeed(16),
    },
    habits: {
      scrolling_speed: 'medium',
      typing_speed: 'medium',
      speech_patterns: [],
      topics_of_interest: dbIdentity.interests ?? [],
      active_hours_start: 8,
      active_hours_end: 22,
      session_duration_min: 10,
      session_duration_max: 30,
      posts_per_day: 3,
      like_ratio: 0.5,
    },
    status: dbIdentity.status,
    created_at: dbIdentity.created_at,
  }
}


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

// How many identities generate concurrently at once - the rest queue and
// pick up a slot as soon as one finishes (success or failure), rather than
// firing all of them at the same time. Keeps the load on the proxy pool
// (and the free-proxy-list scrape/test endpoints) bounded regardless of how
// large a batch is requested, and keeps each identity's own proxy search
// fast (testing against a smaller in-flight contention window).
const BATCH_CONCURRENCY = 7

// Generation runs in bundles of BATCH_CONCURRENCY, so a large requested
// count no longer means that many identities hammering the proxy pool at
// once - this cap just guards against a wildly oversized accidental input,
// not real concurrency.
const MAX_BATCH_GENERATE = 50

interface BatchItem {
  status: 'pending' | 'running' | 'done' | 'error'
  message: string
}

function GenerateModal({
  proxies, proxiesLoading,
  usedProxyIds,
  emailPlatforms,
  onGenerate, onClose,
}: {
  proxies: Proxy[]
  proxiesLoading: boolean
  usedProxyIds: string[]
  emailPlatforms: EmailPlatform[]
  onGenerate: (
    country: string,
    emailPlatformId: string,
    count: number,
    onItemUpdate: (index: number, status: 'running' | 'done' | 'error', message: string) => void,
  ) => void | Promise<void>
  onClose: () => void
}) {
  const [country, setCountry]   = useState('')
  const [emailPlatformId, setEmailPlatformId] = useState('')
  const [count, setCount] = useState(1)
  const [generating, setGenerating] = useState(false)
  const [batchDone, setBatchDone] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)
  const [items, setItems] = useState<BatchItem[]>([])

  async function handleGenerateClick() {
    setGenerating(true)
    setBatchDone(false)
    setGenerateError(null)
    setItems(Array.from({ length: count }, () => ({ status: 'pending', message: 'Waiting…' })))
    try {
      await onGenerate(country, emailPlatformId, count, (index, status, message) => {
        setItems(prev => {
          const next = [...prev]
          next[index] = { status, message }
          return next
        })
      })
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : 'Failed to generate identities')
    } finally {
      setGenerating(false)
      setBatchDone(true)
    }
  }

  // Free proxies: healthy, residential or mobile, and not already assigned
  // by backend or existing identity. Datacenter ranges are far more likely
  // to already be flagged by a site's anti-abuse heuristics, so identities
  // never get assigned one.
  const freeProxies = proxies.filter(p =>
    p.is_healthy && (p.type === 'residential' || p.type === 'mobile') && !p.assigned_bot_id && !usedProxyIds.includes(p.id)
  )

  // Proxy check for chosen country. Not a hard per-country gate any more -
  // generation live-tests candidates and, per "try all proxies in the list
  // if necessary", falls back to any other free proxy if the requested
  // country's own ones don't pan out, so the only real blocker left is
  // having no free residential/mobile proxies at all.
  const proxyCheck = (() => {
    if (proxiesLoading) return { ok: false, msg: 'Loading proxies…' }
    if (freeProxies.length === 0) return { ok: false, msg: 'No healthy unassigned residential/mobile proxies available. Add proxies in the Proxies page.' }
    return { ok: true, msg: '' }
  })()

  const skCount = freeProxies.filter(p => p.country.toUpperCase() === 'SK').length

  const canGenerate = proxyCheck.ok && !!emailPlatformId && !generating && count >= 1

  return (
    <Modal title={count > 1 ? `Generate ${count} Identities` : 'Generate Identity'} isOpen onClose={onClose}
      footer={
        <div className="flex flex-col items-end gap-2">
          {batchDone && items.length > 0 && (
            <p className="text-xs text-gray-400 text-right max-w-sm">
              {items.filter(i => i.status === 'done').length}/{items.length} started successfully
              {items.some(i => i.status === 'error') ? ` — ${items.filter(i => i.status === 'error').length} failed` : ''}
            </p>
          )}
          {generateError && (
            <p className="text-xs text-red-400 text-right max-w-sm">{generateError}</p>
          )}
          <div className="flex justify-end gap-2">
            {batchDone ? (
              <Button onClick={onClose}>Close</Button>
            ) : (
              <>
                <Button variant="ghost" onClick={onClose} disabled={generating}>Cancel</Button>
                <Button disabled={!canGenerate} onClick={handleGenerateClick}>
                  {generating ? 'Generating…' : count > 1 ? `Generate ${count} identities` : 'Generate'}
                </Button>
              </>
            )}
          </div>
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

        {/* Batch count */}
        <div>
          <label className="text-xs text-gray-500 block mb-1.5">
            Number of identities <span className="text-gray-700">— generated in bundles of {BATCH_CONCURRENCY} at a time, the rest queue for a slot</span>
          </label>
          <input
            type="number" min={1} max={MAX_BATCH_GENERATE} value={count}
            disabled={generating}
            onChange={e => setCount(Math.max(1, Math.min(MAX_BATCH_GENERATE, Number(e.target.value) || 1)))}
            className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-300 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {/* Email provider */}
        <div>
          <label className="text-xs text-gray-500 block mb-1.5">
            Email provider <span className="text-gray-700">— a mailbox is created here automatically</span>
          </label>
          <select value={emailPlatformId} onChange={e => setEmailPlatformId(e.target.value)}
            className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-300 focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            <option value="">Select provider…</option>
            {emailPlatforms.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          {emailPlatforms.length === 0 && (
            <p className="text-xs text-red-400 mt-1.5">
              No email providers configured yet. Add one on the Email Accounts page first.
            </p>
          )}
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
                ? `${freeProxies.length} free prox${freeProxies.length !== 1 ? 'ies' : 'y'} available${country === 'SK' ? ` (${skCount} SK)` : ''}` +
                  (count > 1 ? ` — 1 each for ${count} identities` : '')
                : proxyCheck.msg}
            </span>
          </div>

          {/* Email pipeline note */}
          <div className="flex items-start gap-2.5 rounded-lg border border-sky-700/40 bg-sky-900/10 px-3 py-2.5 text-xs text-sky-400">
            <span className="shrink-0 mt-0.5">i</span>
            <span>
              A mailbox with the selected provider is created automatically right after the
              identity is generated, and attached once ready. Only providers with an automated
              signup pipeline behind them (currently: Tuta) will actually complete — this runs
              on the machine hosting the backend and needs one manual CAPTCHA step there. Track
              progress on the Pipelines page.
            </span>
          </div>
        </div>

        {/* Per-identity batch progress - one row per requested identity,
            updated live as generateIdentitiesBatch's concurrent tasks report
            in via onItemUpdate. */}
        {items.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs text-gray-500 uppercase tracking-wider">
              {items.length > 1 ? `Progress (${items.length} identities, running concurrently)` : 'Progress'}
            </p>
            <div className="space-y-1.5 max-h-56 overflow-y-auto">
              {items.map((item, i) => (
                <div key={i} className="flex items-center gap-2 rounded-lg border border-gray-700/40 bg-gray-800/20 px-3 py-2 text-xs">
                  <span className={`shrink-0 h-2 w-2 rounded-full ${
                    item.status === 'done' ? 'bg-emerald-400'
                      : item.status === 'error' ? 'bg-red-400'
                      : item.status === 'running' ? 'bg-blue-400 animate-pulse'
                      : 'bg-gray-600'
                  }`} />
                  <span className={`shrink-0 text-gray-600 ${items.length > 1 ? '' : 'hidden'}`}>#{i + 1}</span>
                  <span className={`truncate ${item.status === 'error' ? 'text-red-400' : 'text-gray-400'}`}>
                    {item.message}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

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
  const { data: emailPlatforms = [] } = useQuery({
    queryKey: ['email-platforms'],
    queryFn: () => getEmailPlatforms(),
  })
  const { data: identitiesDb = [], refetch: refetchIdentities } = useQuery({
    queryKey: ['identities'],
    queryFn: () => getIdentities(),
    // Keep polling briefly after generation so the attached email shows up
    // once the background Tuta pipeline finishes (it can take a while - it
    // waits on a manually-solved CAPTCHA).
    refetchInterval: 10000,
  })

  const identities: RichIdentity[] = identitiesDb.map((i) => hydrateIdentity(i, proxies, emailAccounts))

  // IDs already committed to existing identities
  const usedProxyIds = identities.flatMap(i => i.proxy_ids ?? [])

  // Generates `count` identities in bundles of BATCH_CONCURRENCY, each
  // independently proxy-selected, created, and pipelined. onItemUpdate
  // reports each one's progress independently by index so the modal can
  // render a live per-item list instead of one shared status line.
  async function generateIdentitiesBatch(
    requestedCountry: string,
    emailPlatformId: string,
    count: number,
    onItemUpdate: (index: number, status: 'running' | 'done' | 'error', message: string) => void,
  ) {
    onItemUpdate(0, 'running', 'Fetching proxy pool…')
    // One fresh fetch shared by the whole batch, rather than N separate
    // ones - is_healthy/assigned_bot_id can change from other identities'
    // generation or the backend's own pipeline runs at any moment, and the
    // whole point of this flow is to not act on stale data.
    const { data: freshProxies = [] } = await refetchProxies()

    // Shared across every identity in this batch - see selectAndVerifyProxies's
    // claimedProxyIds param. Without it, two of these running concurrently
    // could both test-and-pick the exact same proxy. Proxies already
    // committed to consumed_at on the backend never come back healthy from
    // testProxy() again, but this is what stops two identities *within this
    // same batch* from racing on the same still-untested candidate.
    const claimedProxyIds = new Set<string>()

    async function generateOne(index: number) {
      const onProgress = (msg: string) => onItemUpdate(index, 'running', msg)

      const freeProxies = freshProxies.filter(p =>
        p.is_healthy && (p.type === 'residential' || p.type === 'mobile') &&
        !p.assigned_bot_id && !usedProxyIds.includes(p.id) && !claimedProxyIds.has(p.id)
      )

      // Any residential/mobile proxy is fair game regardless of country -
      // see selectAndVerifyProxies. Stops at the first one that tests
      // alive (one is all an identity ever needs), so as soon as this
      // resolves, this identity proceeds straight to creation and pipeline
      // start without waiting on anything else - sibling identities' own
      // proxy searches included, since each runs as its own independent
      // task (see the worker pool below).
      const chosenProxy = await selectAndVerifyProxies(freeProxies, onProgress, claimedProxyIds)
      if (!chosenProxy) {
        throw new Error('No live residential/mobile proxy survived testing - try again or add more proxies.')
      }

      const cc = pickIdentityCountry(requestedCountry, freeProxies)
      const draftIdentity = generateIdentityData(cc, [chosenProxy])

      onProgress('Creating identity…')
      // Persist identity in backend DB first, with no email - omitting it
      // (vs. an existing pooled address) is what tells the backend to kick
      // off the signup pipeline for the chosen provider in the background
      // and attach a mailbox once it's done.
      const created = await createIdentity({
        display_name: draftIdentity.display_name,
        username: draftIdentity.username,
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
        email_platform_id: emailPlatformId,
      })

      onProgress('Assigning proxy & starting email pipeline…')
      // Exclusively this identity's own - never shared with another
      // identity in the same batch (claimedProxyIds already prevented that
      // above) or reused once consumed.
      await updateProxy(chosenProxy.id, { assigned_bot_id: created.id })

      onItemUpdate(index, 'done', `Started — ${draftIdentity.display_name} (proxy ${chosenProxy.host}:${chosenProxy.port})`)
    }

    // Concurrency-limited worker pool: BATCH_CONCURRENCY workers each pull
    // the next not-yet-started index and run it to completion before
    // grabbing another - so at most BATCH_CONCURRENCY identities are ever
    // in flight, and a slot frees up (and the next queued one starts)
    // immediately when any one finishes, rather than waiting for the whole
    // bundle to finish together.
    const results: PromiseSettledResult<void>[] = new Array(count)
    let nextIndex = 0
    async function worker() {
      while (nextIndex < count) {
        const index = nextIndex++
        try {
          await generateOne(index)
          results[index] = { status: 'fulfilled', value: undefined }
        } catch (err) {
          results[index] = { status: 'rejected', reason: err }
        }
      }
    }
    await Promise.all(
      Array.from({ length: Math.min(BATCH_CONCURRENCY, count) }, () => worker())
    )
    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        const reason = result.reason
        onItemUpdate(index, 'error', reason instanceof Error ? reason.message : 'Failed to generate identity')
      }
    })

    // Live-testing candidates may have just marked some newly-dead ones
    // unhealthy in the DB, and every successful item just committed a real
    // assignment - refresh so the rest of the page reflects all of that
    // instead of waiting on the next poll.
    await refetchProxies()
    await refetchIdentities()

    const failures = results.filter(r => r.status === 'rejected').length
    if (failures === count) {
      throw new Error(count === 1 ? 'Failed to generate identity.' : `All ${count} identities failed to generate.`)
    }
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
      await updateEmail(identity.email_id, { used_by_bot_id: null })
      await refetchEmails()
    }

    // Remove identity from backend DB.
    await deleteIdentityApi(id)

    await refetchIdentities()
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
          usedProxyIds={usedProxyIds}
          emailPlatforms={emailPlatforms}
          onGenerate={generateIdentitiesBatch}
          onClose={() => setShowGenerate(false)}
        />
      )}
      {preview && (
        <IdentityDetailModal identity={preview} onClose={() => setPreview(null)} />
      )}
    </div>
  )
}



