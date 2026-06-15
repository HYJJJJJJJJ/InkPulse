<script setup>
import { ref, watch, onMounted } from 'vue'
import { store, toast } from '../store.js'
import { api, bust } from '../api.js'

const photos = ref([])
const pinned = ref('')
const fileInput = ref(null)

async function load() {
  photos.value = await api.get('/api/photos')
  const cfg = await api.get('/api/config')
  pinned.value = cfg.photo_pinned || ''
}
async function upload() {
  const f = fileInput.value?.files?.[0]; if (!f) return
  const fd = new FormData(); fd.append('file', f)
  const r = await fetch('/api/photos', { method: 'POST', body: fd })
  if (!r.ok) { toast('上传失败'); return }
  fileInput.value.value = ''
}
async function del(n) { await api.del('/api/photos/' + encodeURIComponent(n)) }
async function pin(n) { await api.post('/api/config', { photo_pinned: n }) }
async function unpin() { await api.post('/api/config', { photo_pinned: '' }) }

watch(() => store.syncToken, load)
onMounted(load)
</script>

<template>
  <div class="card">
    <h2>照片 <small>（photo 布局用）</small></h2>
    <div v-if="!photos.length" class="empty">还没有照片</div>
    <div class="grid">
      <figure v-for="n in photos" :key="n" class="ph" :class="{ on: n === pinned }">
        <img :src="bust('/photos/' + encodeURIComponent(n), store.syncToken)" />
        <button class="ghost sm del" @click="del(n)">×</button>
        <button class="sm pinbtn" :class="{ accent: n === pinned }"
          @click="n === pinned ? unpin() : pin(n)">
          {{ n === pinned ? '✓ 显示中' : '显示此张' }}
        </button>
      </figure>
    </div>
    <p class="hint" style="margin-top:6px">
      {{ pinned ? `已钉住「${pinned}」, 点「显示中」可恢复自动轮换` : '自动轮换中(每 30 分钟切换); 点某张可固定显示' }}
    </p>
    <div class="row" style="margin-top:12px">
      <input ref="fileInput" type="file" accept="image/*" />
      <button class="accent" @click="upload">上传</button>
    </div>
  </div>
</template>

<style scoped>
.grid { display: flex; flex-wrap: wrap; gap: 10px; }
.ph { position: relative; width: 132px; margin: 0; }
.ph img { width: 132px; height: 80px; object-fit: cover; border-radius: 8px; border: 1px solid var(--line-strong); display: block; }
.ph.on img { outline: 3px solid var(--accent); }
.del { position: absolute; top: 4px; right: 4px; }
.pinbtn { width: 100%; margin-top: 4px; }
</style>
