import { test } from 'node:test'
import assert from 'node:assert/strict'
import { processEvents } from '../lib/chat.js'

test('processEvents accumulates t02 continue content', () => {
  const events = [
    { dataType: 't02', data: { messageType: 'begin' } },
    { dataType: 't02', data: { messageType: 'continue', content: 'hello ' } },
    { dataType: 't02', data: { messageType: 'continue', content: 'world' } },
    { dataType: 't02', data: { messageType: 'end' } }
  ]
  const { answer } = processEvents(events)
  assert.equal(answer, 'hello world')
})

test('processEvents extracts chart metadata from t04', () => {
  const events = [
    { dataType: 't04', data: { template_code: 'temp04', columns: ['a', 'b'], data: [[1, 2]], recommended_questions: ['q1'] } }
  ]
  const { chartMeta } = processEvents(events)
  assert.equal(chartMeta.template_code, 'temp04')
  assert.deepEqual(chartMeta.columns, ['a', 'b'])
  assert.deepEqual(chartMeta.recommended_questions, ['q1'])
})

test('processEvents collects t14 step events', () => {
  const events = [
    { dataType: 't14', data: { stepName: '数据源选择...', status: 'start' } },
    { dataType: 't14', data: { stepName: 'SQL生成', status: 'end' } }
  ]
  const { steps } = processEvents(events)
  assert.equal(steps.length, 2)
  assert.equal(steps[0].stepName, '数据源选择...')
  assert.equal(steps[1].status, 'end')
})

test('processEvents ignores unknown dataTypes', () => {
  const events = [
    { dataType: 't99', data: {} },
    { dataType: 't02', data: { messageType: 'continue', content: 'answer' } }
  ]
  const { answer } = processEvents(events)
  assert.equal(answer, 'answer')
})

test('processEvents returns empty answer and null chartMeta for no-content events', () => {
  const events = [
    { dataType: 't02', data: { messageType: 'begin' } },
    { dataType: 't02', data: { messageType: 'end' } }
  ]
  const { answer, chartMeta } = processEvents(events)
  assert.equal(answer, '')
  assert.equal(chartMeta, null)
})
