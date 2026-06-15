// 统一的 /api 调用封装。所有写操作成功后, 后端会 bump web 令牌,
// SSE 推送回来再触发各处刷新 —— 不再用 setTimeout(refreshPreview)。

async function req(method, url, body) {
  const opt = { method, headers: {} }
  if (body !== undefined) {
    opt.headers['Content-Type'] = 'application/json'
    opt.body = JSON.stringify(body)
  }
  const r = await fetch(url, opt)
  let data = null
  try { data = await r.json() } catch { /* 非 json 响应 */ }
  if (!r.ok) {
    const msg = (data && (data.error || data.detail)) || `HTTP ${r.status}`
    throw new Error(msg)
  }
  return data
}

export const api = {
  get: (u) => req('GET', u),
  post: (u, b) => req('POST', u, b),
  put: (u, b) => req('PUT', u, b),
  del: (u, b) => req('DELETE', u, b),
}

// 给图片 URL 加 cache-busting 戳, 配合 SSE 令牌强制刷新
export const bust = (u, token) => `${u}${u.includes('?') ? '&' : '?'}_=${token}`
