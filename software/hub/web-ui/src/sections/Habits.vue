<script setup>
import { ref, watch, onMounted } from 'vue'
import { store } from '../store.js'
import { api } from '../api.js'

const WEEK = ['一', '二', '三', '四', '五', '六', '日']
const data = ref({ habits: [], week: [], done: {}, today_idx: 0 })
const name = ref('')

async function load() { data.value = await api.get('/api/habits') }
async function add() {
  const n = name.value.trim(); if (!n) return
  await api.post('/api/habits', { name: n }); name.value = ''
}
async function toggle(id, date) { await api.post(`/api/habits/${id}/toggle`, { date }) }
async function del(id) { await api.del(`/api/habits/${id}`) }

watch(() => store.syncToken, load)
onMounted(load)
</script>

<template>
  <div class="card">
    <h2>习惯打卡</h2>
    <div v-if="!data.habits.length" class="empty">还没有习惯</div>
    <div v-for="h in data.habits" :key="h.id" class="list-row">
      <span class="spacer">{{ h.name }}</span>
      <button
        v-for="(d, i) in data.week" :key="d"
        class="hcell" :class="{ on: data.done[h.id] && data.done[h.id][i] }"
        :disabled="i > data.today_idx" :title="d"
        @click="toggle(h.id, d)">{{ WEEK[i] }}</button>
      <button class="ghost sm" @click="del(h.id)">×</button>
    </div>
    <div class="row" style="margin-top:14px">
      <input v-model="name" placeholder="新习惯…" @keydown.enter="add" />
      <button class="accent" @click="add">添加</button>
    </div>
  </div>
</template>

<style scoped>
.hcell {
  width: 28px; height: 28px; padding: 0; font-size: 12px; border-radius: 6px;
  background: var(--paper); color: var(--ink-soft); border: 1px solid var(--line-strong);
}
.hcell.on { background: var(--ink); color: var(--paper-raised); border-color: var(--ink); }
.hcell:disabled { opacity: .3; }
</style>
