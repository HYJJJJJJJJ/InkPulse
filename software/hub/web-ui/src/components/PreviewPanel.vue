<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { store, toast } from '../store.js'
import { api, bust } from '../api.js'

const view = ref('device')        // 'device'=真机当前帧, 'preview'=改完预览
const status = ref(null)          // /api/device/status
const refreshing = ref(false)
const now = ref(Date.now())
let tick = null

const imgSrc = computed(() => {
  const t = store.syncToken
  return view.value === 'device'
    ? bust('/api/device/frame.png', t)
    : bust('/preview.png', t)
})

async function loadStatus() {
  try { status.value = await api.get('/api/device/status') } catch { /* ignore */ }
}

// 设备拉帧距今多久(秒) —— 用本地时钟与 status 推算, 每秒走字
const ageText = computed(() => {
  if (!status.value || status.value.pulled_at == null) return '尚未拉帧'
  const age = Math.max(0, Math.round(now.value / 1000 - status.value.pulled_at))
  if (age < 60) return `设备 ${age}s 前拉帧`
  if (age < 3600) return `设备 ${Math.floor(age / 60)} 分钟前拉帧`
  return `设备 ${Math.floor(age / 3600)} 小时前拉帧`
})

const meta = computed(() => {
  const s = status.value || {}
  const bits = []
  if (s.rssi != null) bits.push(`RSSI ${s.rssi}`)
  if (s.temp != null && s.temp > -50 && s.temp < 80) bits.push(`${s.temp}°C`)
  // 湿度传感器坏时回哨兵值(0 / -100), 只在合理区间显示
  if (s.humidity != null && s.humidity > 0 && s.humidity <= 100) bits.push(`湿度 ${s.humidity}%`)
  return bits.join(' · ')
})

async function refreshScreen() {
  refreshing.value = true
  try {
    await api.post('/api/refresh')
    toast('已请求真机刷新, 约 10s 内上屏')
  } catch (e) { toast('请求失败: ' + e.message) }
  setTimeout(() => { refreshing.value = false }, 2500)
}

// SSE 令牌变化 → 重新拉设备状态(图片靠 imgSrc 的戳自动换)
watch(() => store.syncToken, loadStatus)
onMounted(() => {
  loadStatus()
  tick = setInterval(() => { now.value = Date.now() }, 1000)
})
onUnmounted(() => clearInterval(tick))
</script>

<template>
  <section class="preview card">
    <div class="bar">
      <div class="tabs">
        <button class="tab" :class="{ on: view === 'device' }" @click="view = 'device'">真机当前</button>
        <button class="tab" :class="{ on: view === 'preview' }" @click="view = 'preview'">改完预览</button>
      </div>
      <div class="acts">
        <button class="accent sm" :disabled="refreshing" @click="refreshScreen">
          {{ refreshing ? '已请求 ✓' : '⟳ 刷新屏幕' }}
        </button>
        <button class="ghost sm" title="收起预览" @click="store.previewOpen = false">⊟</button>
      </div>
    </div>

    <div class="screen">
      <img :src="imgSrc" alt="screen" />
    </div>

    <div class="foot">
      <template v-if="view === 'device'">
        <span class="pill">{{ ageText }}</span>
        <span v-if="meta" class="metatext">{{ meta }}</span>
        <span class="spacer"></span>
        <small>这是设备此刻物理显示的那一帧</small>
      </template>
      <template v-else>
        <span class="pill accent">改完预览</span>
        <span class="spacer"></span>
        <small>按当前配置渲染 · 下次设备拉帧将变成这样</small>
      </template>
    </div>
  </section>
</template>

<style scoped>
.preview { position: sticky; top: 14px; z-index: 20; padding: 14px; }
.bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.acts { display: inline-flex; gap: 6px; align-items: center; }
.tabs { display: inline-flex; background: var(--paper); border: 1px solid var(--line-strong); border-radius: 9px; padding: 3px; gap: 3px; }
.tab { background: transparent; color: var(--ink-soft); border: 0; padding: 6px 14px; border-radius: 7px; font-size: 13.5px; }
.tab:hover { opacity: 1; background: transparent; }
.tab.on { background: var(--ink); color: var(--paper-raised); }
.screen {
  background: #fff; border: 1px solid var(--line-strong); border-radius: 8px; overflow: hidden;
  /* 800x480 = 5:3 */ aspect-ratio: 5 / 3; display: flex; align-items: center; justify-content: center;
}
.screen img { width: 100%; height: 100%; object-fit: contain; image-rendering: pixelated; }
.foot { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
.metatext { font-size: 12.5px; color: var(--ink-soft); }
@media (max-width: 760px) { .preview { top: 0; } }
</style>
