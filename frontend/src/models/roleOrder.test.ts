import { describe, expect, it } from 'vitest'
import type { SearchResponse } from '../types'
import { orderPresented } from './roleWorkspace'

const item = (id: string, shown: number) => ({ candidate: { id }, facts: { shown } })
const response = (batches: Record<string, number>): SearchResponse =>
  ({ presentation: Object.fromEntries(Object.entries(batches).map(([id, batch]) => [id, { state: 'presented', source: 'initial', seen: true, stale: false, batch }])) }) as unknown as SearchResponse

const ids = (items: Array<{ candidate: { id: string } }>) => items.map((entry) => entry.candidate.id)

describe('display order of the candidates on screen', () => {
  it('puts the candidate with the most core requirements shown first inside a set', () => {
    const items = [item('a', 1), item('b', 4), item('c', 2), item('d', 3), item('e', 0)]
    expect(ids(orderPresented(items, response({ a: 1, b: 1, c: 1, d: 1, e: 1 })))).toEqual(['b', 'd', 'c', 'a', 'e'])
  })

  it('keeps the existing order for ties (the order the search returned them in)', () => {
    const items = [item('a', 2), item('b', 3), item('c', 2), item('d', 3), item('e', 2)]
    expect(ids(orderPresented(items, response({ a: 1, b: 1, c: 1, d: 1, e: 1 })))).toEqual(['b', 'd', 'a', 'c', 'e'])
  })

  it('keeps sets in the order they were shown, so nothing already on screen moves when more arrives', () => {
    const items = [item('a', 1), item('b', 2), item('c', 4), item('d', 3)]
    // c and d are stronger than a and b but arrived later, in a second set.
    expect(ids(orderPresented(items, response({ a: 1, b: 1, c: 2, d: 2 })))).toEqual(['b', 'a', 'c', 'd'])
  })

  it('does not depend on any decision and adds or removes nobody', () => {
    const items = [item('a', 1), item('b', 3), item('c', 2)]
    const ordered = orderPresented(items, response({ a: 1, b: 1, c: 1 }))
    expect([...ids(ordered)].sort()).toEqual(['a', 'b', 'c'])
    expect(items.map((entry) => entry.candidate.id)).toEqual(['a', 'b', 'c']) // the input is not modified
  })

  it('treats a candidate with no batch recorded as the first set', () => {
    const items = [item('a', 1), item('b', 2)]
    expect(ids(orderPresented(items, { presentation: {} } as unknown as SearchResponse))).toEqual(['b', 'a'])
  })
})
