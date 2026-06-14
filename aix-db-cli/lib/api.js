import { request as httpRequest } from 'node:http'
import { request as httpsRequest } from 'node:https'

function requester(baseUrl) {
  return new URL(baseUrl).protocol === 'https:' ? httpsRequest : httpRequest
}

function defaultPort(url) {
  if (url.port) return Number(url.port)
  return url.protocol === 'https:' ? 443 : 80
}

function jsonRequest(baseUrl, method, path, body, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, baseUrl)
    const bodyStr = body ? JSON.stringify(body) : null
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    if (bodyStr) headers['Content-Length'] = Buffer.byteLength(bodyStr)

    const req = requester(baseUrl)({
      hostname: url.hostname,
      port: defaultPort(url),
      path: url.pathname + url.search,
      method,
      headers
    }, (res) => {
      if (res.statusCode === 401) return reject(new Error('AUTH_EXPIRED'))
      let data = ''
      res.on('data', chunk => { data += chunk })
      res.on('end', () => {
        try {
          resolve(JSON.parse(data))
        } catch {
          reject(new Error('Invalid JSON response from server'))
        }
      })
    })
    req.on('error', reject)
    if (bodyStr) req.write(bodyStr)
    req.end()
  })
}

export async function loginApi(baseUrl, username, password) {
  const json = await jsonRequest(baseUrl, 'POST', '/sanic/user/login', { username, password }, null)
  if (json.code === 200 && json.data?.token) return json.data.token
  throw new Error(json.msg || '登录失败')
}

export async function getDatasources(baseUrl, token) {
  const json = await jsonRequest(baseUrl, 'GET', '/sanic/datasource/list', null, token)
  if (json.code === 200) return json.data || []
  throw new Error(json.msg || 'Failed to fetch datasources')
}

export function parseSSEBuffer(buffer) {
  const parts = buffer.split(/\r?\n\r?\n/)
  const remaining = parts.pop()
  const events = []

  for (const part of parts) {
    const line = part.trim()
    if (!line.startsWith('data:')) continue
    const json = line.replace(/^data:\s*/, '').trim()
    if (!json) continue
    try { events.push(JSON.parse(json)) } catch {}
  }

  return { events, remaining: remaining ?? '' }
}

export async function streamChat(baseUrl, token, { query, datasourceId, qaType = 'DATABASE_QA', timeoutSecs = 180 }, onEvent) {
  return new Promise((resolve, reject) => {
    const url = new URL('/sanic/dify/get_answer', baseUrl)
    const body = JSON.stringify({
      query,
      qa_type: qaType,
      uuid: `aix-db-cli-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      chat_id: '',
      file_list: [],
      datasource_id: datasourceId
    })

    let timer
    const req = requester(baseUrl)({
      hostname: url.hostname,
      port: defaultPort(url),
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
        'Authorization': `Bearer ${token}`,
        'Accept': 'text/event-stream'
      }
    }, (res) => {
      if (res.statusCode === 401) {
        clearTimeout(timer)
        return reject(new Error('AUTH_EXPIRED'))
      }

      let buffer = ''
      res.on('data', (chunk) => {
        buffer += chunk.toString()
        const { events, remaining } = parseSSEBuffer(buffer)
        buffer = remaining
        events.forEach(onEvent)
      })
      res.on('end', () => { clearTimeout(timer); resolve() })
      res.on('error', (err) => { clearTimeout(timer); reject(err) })
    })

    timer = setTimeout(() => { req.destroy(); reject(new Error('TIMEOUT')) }, timeoutSecs * 1000)
    req.on('error', (err) => { clearTimeout(timer); reject(err) })
    req.write(body)
    req.end()
  })
}
