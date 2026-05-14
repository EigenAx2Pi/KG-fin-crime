const CURRENCY_SYMBOLS: Record<string, string> = {
  'Saudi Riyal': 'SAR',
  'US Dollar': 'USD',
  'Euro': 'EUR',
  'UK Pound': 'GBP',
  'British Pound': 'GBP',
  'Swiss Franc': 'CHF',
  'Yen': 'JPY',
  'Australian Dollar': 'AUD',
  'Canadian Dollar': 'CAD',
  'Ruble': 'RUB',
  'Yuan': 'CNY',
  'Bitcoin': 'BTC',
  'Mexican Peso': 'MXN',
  'Brazil Real': 'BRL',
  'Rupee': 'INR',
  'Shekel': 'ILS',
}

export const currencyCode = (name: string | null): string =>
  !name ? '' : (CURRENCY_SYMBOLS[name] ?? name)

export function fmtAmount(value: string | number | null, currency?: string | null): string {
  if (value == null) return '—'
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n)) return '—'
  const body = n.toLocaleString('en-US', { maximumFractionDigits: 2 })
  return currency ? `${body} ${currencyCode(currency)}` : body
}

export function fmtDateShort(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function fmtDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function fmtHours(hours: number | null): string {
  if (hours == null) return '—'
  if (hours < 48) return `${hours}h`
  const days = Math.round(hours / 24)
  return `${days}d`
}

// emoji flags — regional indicator trick: A=🇦, country code "GB" → 🇬🇧
export function countryFlag(code: string | null | undefined): string {
  if (!code || code.length !== 2) return '🏳'
  const base = 127397 // 'A' (65) → 🇦 (127462)
  const cc = code.toUpperCase()
  return String.fromCodePoint(cc.charCodeAt(0) + base, cc.charCodeAt(1) + base)
}

const COUNTRY_NAMES: Record<string, string> = {
  AE: 'United Arab Emirates',
  AU: 'Australia',
  BR: 'Brazil',
  CA: 'Canada',
  CH: 'Switzerland',
  CN: 'China',
  DE: 'Germany',
  ES: 'Spain',
  FR: 'France',
  GB: 'United Kingdom',
  HK: 'Hong Kong',
  IN: 'India',
  IT: 'Italy',
  JP: 'Japan',
  MX: 'Mexico',
  NL: 'Netherlands',
  PL: 'Poland',
  RU: 'Russia',
  SA: 'Saudi Arabia',
  SG: 'Singapore',
  US: 'United States',
}
export const countryName = (code: string | null | undefined): string =>
  (code && COUNTRY_NAMES[code.toUpperCase()]) || code || ''
