import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, dirname } from 'node:path'

const CONFIG_PATH = process.env.AIX_DB_CLI_CONFIG_PATH
  || join(homedir(), '.config', 'aix-db-cli', 'config.json')

export function loadConfig() {
  try {
    return JSON.parse(readFileSync(CONFIG_PATH, 'utf8'))
  } catch {
    return null
  }
}

export function saveConfig(config) {
  mkdirSync(dirname(CONFIG_PATH), { recursive: true })
  writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2), 'utf8')
}

export function isTokenExpired(config) {
  if (!config?.tokenExpiry) return true
  return new Date(config.tokenExpiry) <= new Date()
}

export function clearConfig() {
  try {
    rmSync(CONFIG_PATH, { force: true })
    return true
  } catch {
    return false
  }
}

export function requireAuth() {
  const config = loadConfig()
  if (!config?.token) {
    console.error('Error: 未登录，请运行 aix-db-cli login')
    process.exit(1)
  }
  if (isTokenExpired(config)) {
    console.error('Error: token 已过期，请运行 aix-db-cli login')
    process.exit(1)
  }
  return config
}
