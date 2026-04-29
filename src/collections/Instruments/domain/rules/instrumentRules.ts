/**
 * Instrument domain rules — constants and enums for the Instruments collection.
 * Pure domain logic, no framework imports.
 */

export const INSTRUMENT_TYPES = [
  { label: 'Stock', value: 'stock' },
  { label: 'Sector ETF', value: 'etf_sector' },
  { label: 'International ETF', value: 'etf_international' },
  { label: 'Commodity ETF', value: 'etf_commodity' },
  { label: 'Index', value: 'index' },
] as const

export const UNIVERSES = [
  { label: 'S&P 500', value: 'sp500' },
  { label: 'Domestic Sector', value: 'domestic_sector' },
  { label: 'International', value: 'international' },
  { label: 'Commodity', value: 'commodity' },
  { label: 'Guru Gem', value: 'guru_gem' },
] as const

export const CYCLICAL_TYPES = [
  { label: 'Cyclical', value: 'cyclical' },
  { label: 'Defensive', value: 'defensive' },
  { label: 'Mixed', value: 'mixed' },
] as const

export const MARKET_CAPS = [
  { label: 'Mega Cap (>$200B)', value: 'mega' },
  { label: 'Large Cap ($10-200B)', value: 'large' },
  { label: 'Mid Cap ($2-10B)', value: 'mid' },
  { label: 'Small Cap (<$2B)', value: 'small' },
] as const

/**
 * GICS Sectors — Global Industry Classification Standard
 * 11 sectors as defined by MSCI/S&P.
 */
export const GICS_SECTORS = [
  { label: 'Information Technology', value: 'information_technology' },
  { label: 'Health Care', value: 'health_care' },
  { label: 'Financials', value: 'financials' },
  { label: 'Consumer Discretionary', value: 'consumer_discretionary' },
  { label: 'Consumer Staples', value: 'consumer_staples' },
  { label: 'Industrials', value: 'industrials' },
  { label: 'Energy', value: 'energy' },
  { label: 'Utilities', value: 'utilities' },
  { label: 'Real Estate', value: 'real_estate' },
  { label: 'Materials', value: 'materials' },
  { label: 'Communication Services', value: 'communication_services' },
] as const

/**
 * Canonical sector ETF mapping — used across the entire platform.
 * Single source of truth (replaces hardcoded dicts in SectorFlowEngine).
 */
export const SECTOR_ETF_MAP: Record<string, string> = {
  information_technology: 'XLK',
  health_care: 'XLV',
  financials: 'XLF',
  consumer_discretionary: 'XLY',
  consumer_staples: 'XLP',
  industrials: 'XLI',
  energy: 'XLE',
  utilities: 'XLU',
  real_estate: 'XLRE',
  materials: 'XLB',
  communication_services: 'XLC',
}
