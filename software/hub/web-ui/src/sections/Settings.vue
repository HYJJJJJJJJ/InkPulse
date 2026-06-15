<script setup>
import { ref, watch, onMounted } from 'vue'
import { store, toast } from '../store.js'
import { api } from '../api.js'

const budget = ref(''), limit = ref(''), refresh = ref('')

async function load() {
  const c = await api.get('/api/config')
  budget.value = c.usage_budget_usd ?? ''
  limit.value = c.usage_window_token_limit ?? ''
  refresh.value = c.refresh_periodic_s ?? ''
}
const num = (v) => (v === '' ? null : Number(v))
async function save() {
  try {
    await api.post('/api/config', {
      usage_budget_usd: num(budget.value),
      usage_window_token_limit: num(limit.value),
      refresh_periodic_s: num(refresh.value),
    })
    toast('已保存')
  } catch (e) { toast('保存失败: ' + e.message) }
}

watch(() => store.syncToken, load)
onMounted(load)
</script>

<template>
  <div class="card">
    <h2>参数设置</h2>
    <div class="row"><label class="lb">今日预算 (USD)</label><input v-model="budget" type="number" step="1" placeholder="留空=不启用" /></div>
    <div class="row"><label class="lb">token 上限 (5h)</label><input v-model="limit" type="number" step="100000" /></div>
    <div class="row"><label class="lb">刷新间隔 (秒)</label><input v-model="refresh" type="number" step="60" /></div>
    <button class="accent" style="margin-top:10px" @click="save">保存参数</button>
    <p class="hint" style="margin-top:10px">刷新间隔决定设备多久自动拉一次帧; 预算/上限用于用量 widget 的进度与标红。</p>
  </div>
</template>

<style scoped>
.lb { width: 130px; font-size: 14px; color: var(--ink-soft); flex: 0 0 auto; }
</style>
