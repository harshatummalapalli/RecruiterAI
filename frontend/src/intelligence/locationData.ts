// Deterministic, offline canonical location dataset — no LLM, no third-party
// API calls, no hardcoded custom list. Backed by the `country-state-city`
// package (bundled JSON, MIT-licensed, ISO-3166/ADM1 derived), which was
// added specifically because no location data/dependency previously existed
// in this repo (frontend/package.json had none before this pass).
//
// Every function here returns/matches on CANONICAL FULL NAMES ONLY
// (`.name`) — the package's ISO/abbreviation codes (`.isoCode`) are used
// internally to join country -> state -> city but are never surfaced to the
// UI or sent to the backend. This is what guarantees no "NY"/"CA"/"IND"
// style abbreviation ever leaks into the search boundary.
import { Country, State, City } from 'country-state-city'

export type CountryOption = { name: string; isoCode: string }
export type RegionOption = { name: string; isoCode: string }

const ALL_COUNTRIES: CountryOption[] = Country.getAllCountries().map((c) => ({ name: c.name, isoCode: c.isoCode }))

export function listCountries(): CountryOption[] {
  return ALL_COUNTRIES
}

function countryIsoCode(countryName: string): string | null {
  return ALL_COUNTRIES.find((c) => c.name.toLowerCase() === countryName.trim().toLowerCase())?.isoCode ?? null
}

/** Case-insensitive prefix match, canonical full names only. */
export function searchCountries(query: string, limit = 8): CountryOption[] {
  const q = query.trim().toLowerCase()
  if (q.length < 1) return []
  return ALL_COUNTRIES.filter((c) => c.name.toLowerCase().startsWith(q)).slice(0, limit)
}

/** States/regions for a given canonical country name. Country-dependent —
 * an empty/unrecognized country returns no states. */
export function listStatesForCountry(countryName: string): RegionOption[] {
  const iso = countryIsoCode(countryName)
  if (!iso) return []
  return State.getStatesOfCountry(iso).map((s) => ({ name: s.name, isoCode: s.isoCode }))
}

export function searchStatesForCountry(countryName: string, query: string, limit = 8): RegionOption[] {
  const q = query.trim().toLowerCase()
  if (q.length < 1) return []
  return listStatesForCountry(countryName)
    .filter((s) => s.name.toLowerCase().startsWith(q))
    .slice(0, limit)
}

/** Cities for a given canonical country + state name pair. Depends on BOTH —
 * changing the state must invalidate any previously selected city (handled
 * by the caller clearing city state, not here). */
export function listCitiesForState(countryName: string, stateName: string): string[] {
  const countryIso = countryIsoCode(countryName)
  if (!countryIso) return []
  const state = State.getStatesOfCountry(countryIso).find((s) => s.name.toLowerCase() === stateName.trim().toLowerCase())
  if (!state) return []
  return City.getCitiesOfState(countryIso, state.isoCode).map((c) => c.name)
}

export function searchCitiesForState(countryName: string, stateName: string, query: string, limit = 8): string[] {
  const q = query.trim().toLowerCase()
  if (q.length < 1) return []
  return listCitiesForState(countryName, stateName)
    .filter((city) => city.toLowerCase().startsWith(q))
    .slice(0, limit)
}

/** Country-wide city search, not anchored to one state — used for the
 * remote "specific cities" scope, where a city may be picked without first
 * choosing a single state. Still canonical, still deterministic. */
export function searchCitiesForCountry(countryName: string, query: string, limit = 8): string[] {
  const iso = countryIsoCode(countryName)
  const q = query.trim().toLowerCase()
  if (!iso || q.length < 1) return []
  const seen = new Set<string>()
  const matches: string[] = []
  for (const city of City.getCitiesOfCountry(iso) ?? []) {
    if (city.name.toLowerCase().startsWith(q) && !seen.has(city.name)) {
      seen.add(city.name)
      matches.push(city.name)
      if (matches.length >= limit) break
    }
  }
  return matches
}

/** True when `name` is a canonical country name recognized by the dataset —
 * used to gate submission on a real selection rather than free-typed text. */
export function isKnownCountry(name: string): boolean {
  return countryIsoCode(name) !== null
}

export function isKnownStateForCountry(countryName: string, stateName: string): boolean {
  return listStatesForCountry(countryName).some((s) => s.name.toLowerCase() === stateName.trim().toLowerCase())
}

export function isKnownCityForState(countryName: string, stateName: string, cityName: string): boolean {
  return listCitiesForState(countryName, stateName).some((c) => c.toLowerCase() === cityName.trim().toLowerCase())
}
