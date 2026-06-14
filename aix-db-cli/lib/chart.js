import { mkdirSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)

export const DEFAULT_CHART_DIR = join(homedir(), '.cache', 'aix-db-cli', 'charts')

const CHART_WIDTH = 1200
const CHART_HEIGHT = 720

function buildEchartsOption(template, columns, data) {
  const [dimKey, ...valueKeys] = columns
  const categories = data.map((d) => String(d[dimKey] ?? ''))
  const series = valueKeys.map((k) => ({ name: k, data: data.map((d) => d[k]) }))
  const base = {
    backgroundColor: '#ffffff',
    tooltip: {},
    legend: { top: 20 },
    grid: { left: 80, right: 40, top: 80, bottom: 100 },
    textStyle: { fontFamily: 'PingFang SC, Helvetica, Arial, sans-serif' },
  }
  if (template === 'temp02') {
    return {
      ...base,
      series: [{
        type: 'pie',
        radius: ['35%', '65%'],
        center: ['50%', '55%'],
        label: { formatter: '{b}\n{d}%' },
        data: data.map((d) => ({ name: String(d[dimKey] ?? ''), value: d[valueKeys[0]] })),
      }],
    }
  }
  if (template === 'temp04') {
    return {
      ...base,
      xAxis: { type: 'category', data: categories, axisLabel: { rotate: 30 } },
      yAxis: { type: 'value' },
      series: series.map((s) => ({ ...s, type: 'line', smooth: true })),
    }
  }
  // default: bar chart (temp03 and others)
  return {
    ...base,
    xAxis: { type: 'category', data: categories, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' },
    series: series.map((s) => ({ ...s, type: 'bar' })),
  }
}

function renderTableSvg(columns, data) {
  const rowH = 36
  const colW = Math.floor((CHART_WIDTH - 40) / columns.length)
  const totalH = rowH * (data.length + 1) + 20
  const esc = (s) => String(s ?? '').replace(/[<>&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]))
  const cells = []
  columns.forEach((col, i) => {
    cells.push(
      `<rect x="${20 + i * colW}" y="20" width="${colW}" height="${rowH}" fill="#f3f4f6" stroke="#d1d5db"/>`,
      `<text x="${20 + i * colW + 10}" y="${20 + rowH / 2 + 5}" font-family="PingFang SC, sans-serif" font-size="15" font-weight="600" fill="#111827">${esc(col)}</text>`,
    )
  })
  data.forEach((row, ri) => {
    columns.forEach((col, i) => {
      const y = 20 + rowH * (ri + 1)
      cells.push(
        `<rect x="${20 + i * colW}" y="${y}" width="${colW}" height="${rowH}" fill="#ffffff" stroke="#e5e7eb"/>`,
        `<text x="${20 + i * colW + 10}" y="${y + rowH / 2 + 5}" font-family="PingFang SC, sans-serif" font-size="14" fill="#374151">${esc(row[col])}</text>`,
      )
    })
  })
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${CHART_WIDTH}" height="${totalH}" viewBox="0 0 ${CHART_WIDTH} ${totalH}">${cells.join('')}</svg>`
}

export function renderChartPng(chart, outDir = DEFAULT_CHART_DIR) {
  const { template_code: template, columns, data } = chart
  if (!template || !Array.isArray(columns) || !Array.isArray(data) || data.length === 0) return null

  let svg
  if (template === 'temp01') {
    svg = renderTableSvg(columns, data)
  } else {
    const echarts = require('echarts')
    const inst = echarts.init(null, null, { renderer: 'svg', ssr: true, width: CHART_WIDTH, height: CHART_HEIGHT })
    inst.setOption(buildEchartsOption(template, columns, data))
    svg = inst.renderToSVGString()
    inst.dispose()
  }

  const { Resvg } = require('@resvg/resvg-js')
  const png = new Resvg(svg, {
    fitTo: { mode: 'width', value: CHART_WIDTH },
    font: { loadSystemFonts: true },
  }).render().asPng()

  mkdirSync(outDir, { recursive: true })
  const filename = `chart-${template}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}.png`
  const filepath = join(outDir, filename)
  writeFileSync(filepath, png)
  return filepath
}
