<script setup>
import { store } from '../store.js'

const items = [
  { key: 'overview', label: '总览', icon: '◑' },
  { key: 'screen', label: '屏幕', icon: '▦' },
  { key: 'todos', label: '待办', icon: '✓' },
  { key: 'habits', label: '习惯', icon: '◇' },
  { key: 'events', label: '日程', icon: '◔' },
  { key: 'market', label: '行情', icon: '↗' },
  { key: 'weather', label: '天气', icon: '☂' },
  { key: 'photos', label: '照片', icon: '▣' },
  { key: 'settings', label: '设置', icon: '⚙' },
]
</script>

<template>
  <aside class="side">
    <div class="brand">
      <span class="dot"></span> InkPulse
    </div>
    <nav class="nav">
      <button
        v-for="it in items" :key="it.key"
        class="navbtn" :class="{ on: store.section === it.key }"
        @click="store.section = it.key">
        <span class="ic">{{ it.icon }}</span><span class="lb">{{ it.label }}</span>
      </button>
    </nav>
    <div class="status">
      <span class="pill" :class="{ accent: !store.connected }">
        {{ store.connected ? '● 实时已连' : '○ 重连中' }}
      </span>
    </div>
  </aside>
</template>

<style scoped>
.side {
  background: var(--paper-raised);
  border-right: 1px solid var(--line);
  padding: 18px 14px;
  display: flex; flex-direction: column; gap: 16px;
  position: sticky; top: 0; height: 100vh;
}
.brand { font-size: 18px; font-weight: 700; letter-spacing: .02em; display: flex; align-items: center; gap: 9px; }
.brand .dot { width: 11px; height: 11px; border-radius: 50%; background: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft); }
.nav { display: flex; flex-direction: column; gap: 3px; }
.navbtn {
  display: flex; align-items: center; gap: 11px;
  background: transparent; color: var(--ink-soft); border: 0;
  padding: 9px 12px; border-radius: 9px; text-align: left; width: 100%; font-size: 14.5px;
}
.navbtn:hover { background: var(--paper); opacity: 1; }
.navbtn .ic { width: 18px; text-align: center; color: var(--ink-faint); font-size: 15px; }
.navbtn.on { background: var(--ink); color: var(--paper-raised); }
.navbtn.on .ic { color: var(--paper-raised); }
.status { margin-top: auto; }

@media (max-width: 760px) {
  .side {
    position: sticky; top: 0; height: auto; flex-direction: row; align-items: center;
    gap: 10px; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--line);
    padding: 10px 12px; z-index: 40;
  }
  .brand { font-size: 16px; }
  .brand .dot { display: none; }
  .nav { flex-direction: row; gap: 2px; flex: 1; }
  .navbtn { flex-direction: column; gap: 2px; padding: 6px 9px; font-size: 11px; }
  .navbtn .lb { font-size: 11px; }
  .navbtn .ic { font-size: 16px; }
  .status { display: none; }
}
</style>
