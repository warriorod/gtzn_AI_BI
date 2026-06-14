import { test } from 'node:test'
import assert from 'node:assert/strict'
import { parseSSEBuffer } from '../lib/api.js'

test('parseSSEBuffer extracts t02 events', () => {
  const buffer = [
    'data: {"dataType":"t02","data":{"messageType":"continue","content":"hello"}}',
    '',
    'data: {"dataType":"t02","data":{"messageType":"end"}}',
    '',
    ''
  ].join('\n')
  const { events, remaining } = parseSSEBuffer(buffer)
  assert.equal(events.length, 2)
  assert.equal(events[0].dataType, 't02')
  assert.equal(events[0].data.content, 'hello')
  assert.equal(events[1].data.messageType, 'end')
})

test('parseSSEBuffer keeps incomplete frame as remaining', () => {
  const buffer = 'data: {"dataType":"t02","data":{"messageType":"continue","content":"hi"}}\n\ndata: {"dataType":'
  const { events, remaining } = parseSSEBuffer(buffer)
  assert.equal(events.length, 1)
  assert.ok(remaining.includes('"dataType":'))
})

test('parseSSEBuffer skips malformed JSON', () => {
  const buffer = 'data: not-json\n\ndata: {"dataType":"t02","data":{}}\n\n'
  const { events } = parseSSEBuffer(buffer)
  assert.equal(events.length, 1)
  assert.equal(events[0].dataType, 't02')
})

test('parseSSEBuffer handles CRLF line endings', () => {
  const buffer = 'data: {"dataType":"t02","data":{"messageType":"continue","content":"hi"}}\r\n\r\n'
  const { events } = parseSSEBuffer(buffer)
  assert.equal(events.length, 1)
})

test('parseSSEBuffer returns empty events for empty buffer', () => {
  const { events, remaining } = parseSSEBuffer('')
  assert.equal(events.length, 0)
  assert.equal(remaining, '')
})
