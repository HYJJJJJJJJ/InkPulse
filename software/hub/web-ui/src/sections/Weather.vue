<script setup>
import { ref, watch, onMounted } from 'vue'
import { store, toast } from '../store.js'
import { api } from '../api.js'

const cur = ref(null)
const query = ref('')
const results = ref([])

async function load() { cur.value = await api.get('/api/weather') }
async function search() {
  const q = query.value.trim(); if (!q) return
  results.value = await api.get('/api/weather/search?q=' + encodeURIComponent(q))
  if (!results.value.length) toast('没找到该城市')
}
async function pick(r) {
  await api.post('/api/weather/location', { lat: r.lat, lon: r.lon, name: r.name })
  results.value = []; query.value = ''
}
async function clear() { await api.del('/api/weather/location') }

watch(() => store.syncToken, load)
onMounted(load)
</script>

<template>
  <div class="card">
    <h2>天气地点</h2>
    <div v-if="cur && cur.place" class="list-row">
      <span class="spacer">当前：<b>{{ cur.place }}</b></span>
      <button class="ghost sm" @click="clear">清除</button>
    </div>
    <div v-else class="empty">未设置地点</div>

    <div class="row" style="margin-top:14px">
      <input v-model="query" placeholder="搜索城市, 如 杭州" @keydown.enter="search" />
      <button class="accent" @click="search">搜索</button>
    </div>
    <div v-for="r in results" :key="r.lat + ',' + r.lon" class="list-row">
      <span class="spacer">{{ r.name }} · {{ r.admin || '' }}</span>
      <button class="sm" @click="pick(r)">选择</button>
    </div>
  </div>
</template>
