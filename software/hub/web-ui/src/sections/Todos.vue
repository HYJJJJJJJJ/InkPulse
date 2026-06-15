<script setup>
import { ref, watch, onMounted } from 'vue'
import { store, toast } from '../store.js'
import { api } from '../api.js'

const todos = ref([])
const text = ref('')

async function load() { todos.value = await api.get('/api/todos') }
async function add() {
  const t = text.value.trim(); if (!t) return
  await api.post('/api/todos', { text: t }); text.value = ''
}
async function toggle(id) { await api.post(`/api/todos/${id}/toggle`) }
async function del(id) { await api.del(`/api/todos/${id}`) }

watch(() => store.syncToken, load)
onMounted(load)
</script>

<template>
  <div class="card">
    <h2>待办</h2>
    <div v-if="!todos.length" class="empty">还没有待办</div>
    <div v-for="t in todos" :key="t.id" class="list-row">
      <input type="checkbox" :checked="t.done" @change="toggle(t.id)" />
      <span class="spacer" :class="{ done: t.done }">{{ t.text }}</span>
      <button class="ghost sm" @click="del(t.id)">×</button>
    </div>
    <div class="row" style="margin-top:14px">
      <input v-model="text" placeholder="新待办…" @keydown.enter="add" />
      <button class="accent" @click="add">添加</button>
    </div>
  </div>
</template>

<style scoped>
.done { text-decoration: line-through; color: var(--ink-faint); }
.list-row input[type=checkbox] { width: 17px; height: 17px; accent-color: var(--accent); }
</style>
