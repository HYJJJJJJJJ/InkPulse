import { reactive } from 'vue'

// 全局轻量 store: SSE 推来的 web 同步令牌 + 当前分区 + 一个全局错误条
export const store = reactive({
  section: 'overview',     // 当前侧栏分区
  syncToken: 0,            // SSE web 令牌, 任何数据/配置/拉帧变化都会变
  devicePulledAt: null,    // 设备最近拉帧时间(epoch 秒)
  connected: false,        // SSE 是否在线
  toast: '',               // 一次性提示
  // 预览面板停靠在右侧; 宽屏默认展开, 窄屏默认收起(避免压在内容上方挡路)
  previewOpen: typeof window !== 'undefined' ? window.innerWidth > 1024 : true,
})

let toastTimer = null
export function toast(msg) {
  store.toast = msg
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { store.toast = '' }, 2600)
}

// 订阅后端 SSE; 断线自动重连由 EventSource 负责
export function connectSSE() {
  const es = new EventSource('/api/stream')
  es.onopen = () => { store.connected = true }
  es.onerror = () => { store.connected = false }
  es.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data)
      if (typeof d.token === 'number') store.syncToken = d.token
      if (d.device_pulled_at != null) store.devicePulledAt = d.device_pulled_at
    } catch { /* 心跳/非 json 忽略 */ }
  }
  return es
}
