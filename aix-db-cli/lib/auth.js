import { createServer } from 'node:http'
import { saveConfig } from './config.js'
import { loginApi } from './api.js'
import open from 'open'

const LOGIN_HTML = (baseUrl) => `<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <title>Aix-DB CLI 登录</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; display: flex; justify-content: center;
           align-items: center; min-height: 100vh; background: #f5f5f5; }
    .card { background: white; border-radius: 12px; padding: 40px; width: 360px;
            box-shadow: 0 2px 12px rgba(0,0,0,.08); }
    h2 { font-size: 20px; margin-bottom: 8px; color: #111; }
    .server { font-size: 13px; color: #888; margin-bottom: 28px; word-break: break-all; }
    label { display: block; font-size: 13px; color: #555; margin-bottom: 4px; }
    input { display: block; width: 100%; padding: 9px 12px; margin-bottom: 16px;
            border: 1px solid #ddd; border-radius: 8px; font-size: 15px; outline: none; }
    input:focus { border-color: #2563eb; }
    button { width: 100%; padding: 11px; background: #2563eb; color: white;
             border: none; border-radius: 8px; font-size: 15px; cursor: pointer; font-weight: 500; }
    button:hover { background: #1d4ed8; }
    button:disabled { background: #93c5fd; cursor: not-allowed; }
    .error { color: #dc2626; font-size: 13px; margin-top: 12px; display: none; }
    .success { text-align: center; padding: 40px 0; }
    .success h2 { color: #16a34a; font-size: 22px; }
    .success p { color: #555; margin-top: 8px; font-size: 14px; }
  </style>
</head>
<body>
  <div class="card" id="card">
    <h2>Aix-DB CLI 登录</h2>
    <div class="server">${baseUrl}</div>
    <form id="form">
      <label>用户名</label>
      <input type="text" id="username" value="admin" required autocomplete="username" />
      <label>密码</label>
      <input type="password" id="password" value="123456" required autocomplete="current-password" />
      <button type="submit" id="btn">登录</button>
      <div class="error" id="err"></div>
    </form>
  </div>
  <script>
    document.getElementById('form').onsubmit = async (e) => {
      e.preventDefault()
      const btn = document.getElementById('btn')
      const err = document.getElementById('err')
      btn.disabled = true
      btn.textContent = '登录中...'
      err.style.display = 'none'
      try {
        const res = await fetch('/do-login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: document.getElementById('username').value,
            password: document.getElementById('password').value
          })
        })
        const data = await res.json()
        if (data.ok) {
          document.getElementById('card').innerHTML =
            '<div class="success"><h2>✓ 登录成功</h2><p>可以关闭此窗口了</p></div>'
        } else {
          err.textContent = data.error || '登录失败，请检查用户名和密码'
          err.style.display = 'block'
          btn.disabled = false
          btn.textContent = '登录'
        }
      } catch {
        err.textContent = '网络错误，请确认服务地址正确'
        err.style.display = 'block'
        btn.disabled = false
        btn.textContent = '登录'
      }
    }
  </script>
</body>
</html>`

export async function loginCommand(baseUrl) {
  return new Promise((resolve, reject) => {
    const server = createServer(async (req, res) => {
      if (req.method === 'GET' && req.url === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
        res.end(LOGIN_HTML(baseUrl))
        return
      }

      if (req.method === 'POST' && req.url === '/do-login') {
        let body = ''
        req.on('data', chunk => {
          body += chunk
          if (body.length > 10 * 1024) {
            req.destroy()
          }
        })
        req.on('end', async () => {
          try {
            const { username, password } = JSON.parse(body)
            const token = await loginApi(baseUrl, username, password)
            const tokenExpiry = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString()
            saveConfig({ baseUrl, token, tokenExpiry })
            res.writeHead(200, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify({ ok: true }))
            server.close()
            resolve()
          } catch (err) {
            res.writeHead(200, { 'Content-Type': 'application/json' })
            res.end(JSON.stringify({ ok: false, error: err.message }))
          }
        })
        return
      }

      res.writeHead(404)
      res.end()
    })

    server.listen(0, '127.0.0.1', async () => {
      const port = server.address().port
      const url = `http://127.0.0.1:${port}/`
      console.log(`\n正在打开浏览器: ${url}`)
      console.log('请在浏览器中完成登录...\n')
      await open(url)
    })

    server.on('error', reject)
  })
}
