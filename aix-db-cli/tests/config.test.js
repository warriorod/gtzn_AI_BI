import { test, after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

const tmpDir = join(tmpdir(), `aix-db-cli-test-${Date.now()}`)
const testConfigPath = join(tmpDir, 'config.json')
process.env.AIX_DB_CLI_CONFIG_PATH = testConfigPath

const { loadConfig, saveConfig, isTokenExpired } = await import('../lib/config.js')

test('loadConfig returns null when file does not exist', () => {
  const result = loadConfig()
  assert.equal(result, null)
})

test('saveConfig and loadConfig round-trip', () => {
  mkdirSync(tmpDir, { recursive: true })
  const config = {
    baseUrl: 'http://localhost:18080',
    token: 'abc',
    tokenExpiry: '2099-01-01T00:00:00.000Z'
  }
  saveConfig(config)
  const loaded = loadConfig()
  assert.deepEqual(loaded, config)
})

test('isTokenExpired returns true for past date', () => {
  assert.equal(isTokenExpired({ tokenExpiry: '2020-01-01T00:00:00.000Z' }), true)
})

test('isTokenExpired returns false for future date', () => {
  assert.equal(isTokenExpired({ tokenExpiry: '2099-01-01T00:00:00.000Z' }), false)
})

test('isTokenExpired returns true for missing tokenExpiry', () => {
  assert.equal(isTokenExpired({}), true)
  assert.equal(isTokenExpired(null), true)
})

after(() => {
  rmSync(tmpDir, { recursive: true, force: true })
})
