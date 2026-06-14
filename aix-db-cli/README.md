# @apconw/aix-db-cli

Aix-DB 数据问答命令行工具。通过浏览器登录后，直接在终端发起自然语言数据查询，支持图表渲染输出。

[![npm version](https://img.shields.io/npm/v/@apconw/aix-db-cli)](https://www.npmjs.com/package/@apconw/aix-db-cli)
[![Node >=18](https://img.shields.io/badge/node-%3E%3D18-brightgreen)](https://nodejs.org)
[![GitHub stars](https://img.shields.io/github/stars/apconw/Aix-DB?style=social)](https://github.com/apconw/Aix-DB)

> 基于 [Aix-DB](https://github.com/apconw/Aix-DB) 开源项目 —— LLM 驱动的数据分析平台（ChatBI）。如果对你有帮助，欢迎给项目点个 ⭐️

## 安装

```bash
npm install -g @apconw/aix-db-cli
```

## 快速开始

```bash
# 1. 登录（浏览器完成认证，token 有效期 7 天）
aix-db-cli login

# 自定义服务地址
aix-db-cli login --url http://your-server:18080

# 2. 查看可用数据源
aix-db-cli datasources

# 按类型过滤
aix-db-cli datasources --type mysql

# 3. 数据问答
aix-db-cli chat "有哪些数据表？" --datasource 48

# 流式输出（逐字打印）
aix-db-cli chat "查询销售额趋势" --datasource 48 --stream

# 显示执行步骤（SQL 生成过程）
aix-db-cli chat "各表行数统计" --datasource 48 --verbose

# 4. 退出登录
aix-db-cli logout
```

## 命令

### `login`

打开浏览器完成登录，将 JWT token 保存到本地（有效期 7 天）。

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--url <baseUrl>` | `http://localhost:18080` | Aix-DB 服务地址 |

### `logout`

清除本地登录状态（删除保存的 token）。

### `datasources`

列出已注册的数据源。

| 选项 | 说明 |
|------|------|
| `--type <type>` | 按类型精确过滤（mysql, pg, ck, starrocks, oracle...）|
| `--name <name>` | 按名称模糊过滤 |

**输出示例：**

```
ID     NAME             TYPE         STATUS     HOST                     DATABASE
48     mysql            MySQL        Success    host.docker.internal     chat_db
51     starrocks        StarRocks    Success    10.0.0.1                 analytics
```

### `chat <question>`

用自然语言发起数据问答，答案输出到 stdout，图表自动渲染为 PNG 文件。

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--datasource <id>` | 必填 | 数据源 ID（见 `datasources` 命令）|
| `--qa-type <type>` | `DATABASE_QA` | 问答模式 |
| `--timeout <seconds>` | `180` | 超时时间（秒）|
| `--verbose` | false | 显示 SQL 生成等执行步骤 |
| `--stream` | false | 流式逐字输出 |
| `--no-render-chart` | — | 跳过图表渲染，只显示文字结果 |
| `--chart-dir <dir>` | `~/.cache/aix-db-cli/charts` | 图表 PNG 输出目录 |

**输出示例：**

```
问题: 统计销售额按分类分组
数据源: 48
---
电子产品销售额 42,681 元，占比 75.3%
家电 8,240 元，服装 4,727 元

[图表: temp02 — 2 列 × 4 行]
图表文件: /Users/you/.cache/aix-db-cli/charts/chart-temp02-1748xxx.png

推荐问题:
  1. 各分类环比增长率如何？
  2. 哪个分类利润率最高？
```

## 图表支持

| 模板 | 类型 |
|------|------|
| `temp01` | 表格 |
| `temp02` | 饼图 |
| `temp03` | 柱状图 |
| `temp04` | 折线图 |

图表使用 ECharts SSR + Resvg 渲染为 PNG，支持中文字体。

## 配置文件

登录信息保存在 `~/.config/aix-db-cli/config.json`，包含服务地址和 token，有效期 7 天。

## 系统要求

- Node.js ≥ 18
- 已部署的 [Aix-DB](https://github.com/apconw/Aix-DB) 服务

## 相关链接

- 🏠 项目主页：[https://github.com/apconw/Aix-DB](https://github.com/apconw/Aix-DB)
- 📦 npm 包：[https://www.npmjs.com/package/@apconw/aix-db-cli](https://www.npmjs.com/package/@apconw/aix-db-cli)
- 🐛 问题反馈：[https://github.com/apconw/Aix-DB/issues](https://github.com/apconw/Aix-DB/issues)
