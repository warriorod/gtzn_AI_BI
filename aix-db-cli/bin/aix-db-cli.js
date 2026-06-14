#!/usr/bin/env node
import { Command } from 'commander'
import { loginCommand } from '../lib/auth.js'
import { clearConfig, loadConfig } from '../lib/config.js'
import { datasourcesCommand } from '../lib/datasources.js'
import { chatCommand } from '../lib/chat.js'
import { DEFAULT_CHART_DIR } from '../lib/chart.js'

const program = new Command()

program
  .name('aix-db-cli')
  .description('Aix-DB 数据问答 CLI')
  .version('0.1.0')

program
  .command('login')
  .description('浏览器登录并保存 token（有效期 7 天）')
  .option('--url <baseUrl>', '服务地址', 'http://localhost:18080')
  .action(async (opts) => {
    try {
      await loginCommand(opts.url)
      console.log('✓ 登录成功，token 有效期 7 天')
    } catch (err) {
      console.error(`登录失败: ${err.message}`)
      process.exit(1)
    }
  })

program
  .command('logout')
  .description('清除本地登录状态')
  .action(() => {
    const config = loadConfig()
    if (!config?.token) {
      console.log('当前未登录')
      return
    }
    clearConfig()
    console.log('✓ 已退出登录')
  })

program
  .command('datasources')
  .description('列出可用数据源')
  .option('--type <type>', '按类型过滤 (mysql, ck, starrocks, pg...)')
  .option('--name <name>', '按名称模糊过滤')
  .action(async (opts) => {
    try {
      await datasourcesCommand(opts)
    } catch (err) {
      console.error(`Error: ${err.message}`)
      process.exit(1)
    }
  })

program
  .command('chat <question>')
  .description('数据问答（DATABASE_QA）')
  .requiredOption('--datasource <id>', '数据源 ID（见 datasources 命令）')
  .option('--qa-type <type>', '问答模式', 'DATABASE_QA')
  .option('--timeout <seconds>', '超时时间（秒）', '180')
  .option('--verbose', '显示执行步骤', false)
  .option('--stream', '流式输出（逐字打印）', false)
  .option('--no-render-chart', '不渲染图表文件')
  .option('--chart-dir <dir>', '图表输出目录', DEFAULT_CHART_DIR)
  .action(async (question, opts) => {
    try {
      await chatCommand(question, opts)
    } catch (err) {
      console.error(`Error: ${err.message}`)
      process.exit(1)
    }
  })

program.parse()
