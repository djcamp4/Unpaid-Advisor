import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import assert from 'node:assert/strict'
import { test } from 'node:test'

function setup() {
  let source
  class EventSource {
    constructor() { source = this; this.closed = false }
    close() { this.closed = true }
  }
  const code = readFileSync(new URL('./src/api.js', import.meta.url), 'utf8')
    .split('export function startStockSelector')[1]
  const context = vm.createContext({ EventSource, BASE: '' })
  vm.runInContext('function startStockSelector' + code, context)
  const events = []
  const cleanup = context.startStockSelector(event => events.push(event))
  return { source, events, cleanup }
}

test('terminal events close once and ignore subsequent disconnect', () => {
  for (const type of ['complete', 'error']) {
    const { source, events } = setup()
    source.onmessage({ data: JSON.stringify({ type }) })
    source.onerror()
    assert.equal(source.closed, true)
    assert.equal(events.length, 1)
    assert.equal(events[0].type, type)
  }
})

test('interrupted partial results do not pretend the scan completed', () => {
  const { source, events } = setup()
  source.onmessage({ data: '{"type":"found"}' })
  source.onerror()
  source.onerror()
  assert.equal(events.length, 2)
  assert.equal(events[1].type, 'error')
})

test('cleanup suppresses late callbacks', () => {
  const { source, events, cleanup } = setup()
  cleanup()
  source.onerror()
  source.onmessage({ data: '{"type":"complete"}' })
  assert.equal(events.length, 0)
})
