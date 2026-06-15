<script setup>
import { ref, watch, onMounted } from 'vue'
import { store } from '../store.js'
import { api } from '../api.js'

const s = ref({ todos: 0, todosDone: 0, habits: 0, events: 0, market: 0, place: '', layout: '' })

async function load() {
  const [todos, habits, events, market, cfg] = await Promise.all([
    api.get('/api/todos'), api.get('/api/habits'), api.get('/api/events'),
    api.get('/api/market/symbols'), api.get('/api/config'),
  ])
  s.value = {
    todos: todos.length,
    todosDone: todos.filter((t) => t.done).length,
    habits: habits.habits.length,
    events: events.length,
    market: market.length,
    place: cfg.weather_place || '未设置',
    layout: cfg.layout_name || '',
  }
}
function go(sec) { store.section = sec }

watch(() => store.syncToken, load)
onMounted(load)
</script>

<template>
  <div class="card">
    <h2>总览</h2>
    <div class="tiles">
      <button class="tile" @click="go('todos')">
        <div class="num">{{ s.todosDone }}/{{ s.todos }}</div><div class="cap">待办完成</div>
      </button>
      <button class="tile" @click="go('habits')">
        <div class="num">{{ s.habits }}</div><div class="cap">习惯</div>
      </button>
      <button class="tile" @click="go('events')">
        <div class="num">{{ s.events }}</div><div class="cap">日程</div>
      </button>
      <button class="tile" @click="go('market')">
        <div class="num">{{ s.market }}</div><div class="cap">行情标的</div>
      </button>
      <button class="tile" @click="go('weather')">
        <div class="num sm">{{ s.place }}</div><div class="cap">天气地点</div>
      </button>
      <button class="tile" @click="go('screen')">
        <div class="num sm">{{ s.layout }}</div><div class="cap">当前布局</div>
      </button>
    </div>
    <p class="hint" style="margin-top:14px">上方常驻面板即「真机当前帧」—— 设备此刻物理显示的内容; 切到「改完预览」可看改动后的效果。任意修改都会经 SSE 即时反映, 无需手动刷新。</p>
  </div>
</template>

<style scoped>
.tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }
.tile {
  background: var(--paper); border: 1px solid var(--line); color: var(--ink);
  border-radius: 12px; padding: 16px; text-align: left; display: flex; flex-direction: column; gap: 4px;
}
.tile:hover { border-color: var(--accent); background: var(--accent-soft); opacity: 1; }
.num { font-size: 26px; font-weight: 700; }
.num.sm { font-size: 17px; font-weight: 600; }
.cap { font-size: 12.5px; color: var(--ink-faint); }
</style>
