import { requireAuth } from './config.js'
import { getDatasources } from './api.js'

function pad(value, width) {
  return String(value ?? '').slice(0, width).padEnd(width)
}

export async function datasourcesCommand({ type, name } = {}) {
  const config = requireAuth()

  let rows
  try {
    rows = await getDatasources(config.baseUrl, config.token)
  } catch (err) {
    if (err.message === 'AUTH_EXPIRED') {
      console.error('Error: token 已过期，请运行 aix-db-cli login')
      process.exit(1)
    }
    console.error(`Error: ${err.message}`)
    process.exit(1)
  }

  if (type) rows = rows.filter(r => r.type?.toLowerCase() === type.toLowerCase())
  if (name) rows = rows.filter(r => r.name?.toLowerCase().includes(name.toLowerCase()))

  if (rows.length === 0) {
    console.error('Error: 未找到匹配的数据源')
    process.exit(1)
  }

  const cols = [
    { key: 'id',        label: 'ID',       width: 6  },
    { key: 'name',      label: 'NAME',     width: 16 },
    { key: 'type_name', label: 'TYPE',     width: 12 },
    { key: 'status',    label: 'STATUS',   width: 10 },
    { key: 'host',      label: 'HOST',     width: 24 },
    { key: 'database',  label: 'DATABASE', width: 16 }
  ]

  console.log(cols.map(c => pad(c.label, c.width)).join(' '))
  console.log(cols.map(c => '-'.repeat(c.width)).join(' '))
  for (const row of rows) {
    console.log(cols.map(c => pad(row[c.key], c.width)).join(' '))
  }
}
