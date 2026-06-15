<script setup>
import { ref, watch, onMounted } from 'vue'
import { store, toast } from '../store.js'
import { api } from '../api.js'

const LABEL = { cn: 'A股/指数', crypto: '加密' }
const symbols = ref([])
const type = ref('cn'), code = ref('')

async function load() { symbols.value = await api.get('/api/market/symbols') }
async function add() {
  if (!code.value.trim()) { toast('请填代码'); return }
  try { await api.post('/api/market/symbols', { type: type.value, code: code.value.trim() }); code.value = '' }
  catch (e) { toast('添加失败: ' + e.message) }
}
async function del(s) { await api.del('/api/market/symbols', { type: s.type, code: s.code }) }

watch(() => store.syncToken, load)
onMounted(load)
</script>

<template>
  <div class="card">
    <h2>行情</h2>
    <div v-if="!symbols.length" class="empty">还没有标的</div>
    <div v-for="s in symbols" :key="s.type + s.code" class="list-row">
      <span class="pill">{{ LABEL[s.type] || s.type }}</span>
      <span class="spacer">{{ s.code }}</span>
      <button class="ghost sm" @click="del(s)">×</button>
    </div>
    <div class="row" style="margin-top:14px">
      <select v-model="type" style="flex:0 0 auto">
        <option value="cn">A股/指数</option>
        <option value="crypto">加密</option>
      </select>
      <input v-model="code" placeholder="代码: sh000001 / sh600519 / BTC-USDT" @keydown.enter="add" />
      <button class="accent" @click="add">添加</button>
    </div>
  </div>
</template>
