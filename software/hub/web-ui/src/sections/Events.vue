<script setup>
import { ref, watch, onMounted } from 'vue'
import { store, toast } from '../store.js'
import { api } from '../api.js'

const events = ref([])
const title = ref(''), date = ref(''), time = ref('')

async function load() { events.value = await api.get('/api/events') }
async function add() {
  if (!title.value.trim() || !date.value) { toast('请填标题和日期'); return }
  try {
    await api.post('/api/events', { title: title.value.trim(), date: date.value, time: time.value })
    title.value = ''; time.value = ''
  } catch (e) { toast('添加失败: ' + e.message) }
}
async function del(id) { await api.del(`/api/events/${id}`) }

watch(() => store.syncToken, load)
onMounted(load)
</script>

<template>
  <div class="card">
    <h2>日程</h2>
    <div v-if="!events.length" class="empty">还没有日程</div>
    <div v-for="e in events" :key="e.id" class="list-row">
      <span class="spacer"><b>{{ e.date }}</b> {{ e.time || '全天' }} · {{ e.title }}</span>
      <button class="ghost sm" @click="del(e.id)">×</button>
    </div>
    <div class="row" style="margin-top:14px">
      <input v-model="title" placeholder="日程标题…" style="flex:2" />
      <input v-model="date" type="date" />
      <input v-model="time" type="time" />
      <button class="accent" @click="add">添加</button>
    </div>
  </div>
</template>
