import { requireAuth } from './config.js'
import { streamChat } from './api.js'
import { renderChartPng, DEFAULT_CHART_DIR } from './chart.js'

export function processEvents(events) {
  let answer = ''
  let chartMeta = null
  const steps = []

  for (const event of events) {
    const { dataType, data } = event
    if (dataType === 't02') {
      if (data?.messageType === 'continue' && data.content) {
        answer += data.content
      }
    }
    if (dataType === 't04' && data) {
      chartMeta = data
    }
    if (dataType === 't14') {
      steps.push({ stepName: data?.stepName, status: data?.status })
    }
  }

  return { answer, chartMeta, steps }
}

export async function chatCommand(question, { datasource, qaType, timeout, verbose, stream, renderChart = true, chartDir = DEFAULT_CHART_DIR }) {
  const config = requireAuth()

  const collectedEvents = []

  try {
    await streamChat(
      config.baseUrl,
      config.token,
      {
        query: question,
        datasourceId: Number(datasource),
        qaType,
        timeoutSecs: Number(timeout)
      },
      (event) => {
        collectedEvents.push(event)

        if (stream && event.dataType === 't02' && event.data?.messageType === 'continue' && event.data.content) {
          process.stdout.write(event.data.content)
        }

        if (event.dataType === 't02' && event.data?.messageType === 'error') {
          console.error(`\nError: ${event.data.content}`)
          process.exit(1)
        }

        if (verbose && event.dataType === 't14') {
          const step = event.data?.stepName || ''
          const status = event.data?.status || ''
          process.stderr.write(`[步骤] ${step} ${status}\n`)
        }
      }
    )
  } catch (err) {
    if (err.message === 'TIMEOUT') {
      console.error(`Error: 请求超时 (${timeout}s)，请重试`)
      process.exit(1)
    }
    if (err.message === 'AUTH_EXPIRED') {
      console.error('Error: token 已过期，请运行 aix-db-cli login')
      process.exit(1)
    }
    console.error(`Error: ${err.message}`)
    process.exit(1)
  }

  const { answer, chartMeta } = processEvents(collectedEvents)

  if (!answer.trim()) {
    console.error('Error: 未获得有效答案')
    process.exit(1)
  }

  if (!stream) {
    console.log(`问题: ${question}`)
    console.log(`数据源: ${datasource}`)
    console.log('---')
    console.log(answer)
  } else {
    process.stdout.write('\n')
  }

  if (chartMeta) {
    const template = chartMeta.template_code || 'unknown'
    const cols = Array.isArray(chartMeta.columns) ? chartMeta.columns.length : 0
    const dataRows = Array.isArray(chartMeta.data) ? chartMeta.data.length : 0
    console.log(`\n[图表: ${template} — ${cols} 列 × ${dataRows} 行]`)

    if (renderChart) {
      try {
        const chartFile = renderChartPng(chartMeta, chartDir)
        if (chartFile) {
          console.log(`图表文件: ${chartFile}`)
        }
      } catch (err) {
        console.error(`图表渲染失败: ${err.message}`)
      }
    }

    if (Array.isArray(chartMeta.recommended_questions) && chartMeta.recommended_questions.length > 0) {
      console.log('\n推荐问题:')
      chartMeta.recommended_questions.forEach((q, i) => console.log(`  ${i + 1}. ${q}`))
    }
  }
}
