<script setup>
import { onMounted, onUnmounted, computed } from 'vue'
import { store, connectSSE } from './store.js'
import Sidebar from './components/Sidebar.vue'
import PreviewPanel from './components/PreviewPanel.vue'

import Overview from './sections/Overview.vue'
import Screen from './sections/Screen.vue'
import Todos from './sections/Todos.vue'
import Habits from './sections/Habits.vue'
import Events from './sections/Events.vue'
import Market from './sections/Market.vue'
import Weather from './sections/Weather.vue'
import Photos from './sections/Photos.vue'
import Settings from './sections/Settings.vue'

const sections = {
  overview: Overview, screen: Screen, todos: Todos, habits: Habits,
  events: Events, market: Market, weather: Weather, photos: Photos, settings: Settings,
}
const current = computed(() => sections[store.section] || Overview)
const isOverview = computed(() => store.section === 'overview')

let es = null
onMounted(() => { es = connectSSE() })
onUnmounted(() => { es && es.close() })
</script>

<template>
  <div class="app">
    <Sidebar />
    <main class="main">
      <div class="workspace" :class="{ collapsed: !store.previewOpen, hero: isOverview }">
        <div class="content">
          <component :is="current" :key="store.section" />
        </div>
        <PreviewPanel v-show="store.previewOpen" class="dock" />
      </div>
      <button v-if="!store.previewOpen" class="reveal" @click="store.previewOpen = true">◧ 显示预览</button>
    </main>
    <Transition name="fade">
      <div v-if="store.toast" class="toast">{{ store.toast }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.app {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  min-height: 100vh;
}
.main {
  min-width: 0;
  padding: 20px;
  width: 100%;
}
/* 内容在左、预览停靠在右(并排, 不挡内容); 收起时单列 */
.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  gap: 20px;
  align-items: start;
  max-width: 1240px;
  margin: 0 auto;
}
.workspace.collapsed { grid-template-columns: minmax(0, 1fr); max-width: 880px; }
/* 总览: 真机帧当主角 —— 放大置顶, 占满内容宽度, 磁贴在下方 */
.workspace.hero { grid-template-columns: 1fr; max-width: 960px; }
.workspace.hero .dock { order: -1; }
.content { min-width: 0; }
.dock { min-width: 0; }
.reveal {
  position: fixed; right: 18px; bottom: 22px; z-index: 30;
  box-shadow: var(--shadow); border-radius: 10px;
}
.toast {
  position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%);
  background: var(--ink); color: var(--paper-raised);
  padding: 10px 18px; border-radius: 10px; box-shadow: var(--shadow);
  font-size: 14px; z-index: 50;
}
/* 中等屏: 预览撤到内容上方前先收起更合适 → 单列, 预览(若开)回到顶部 */
@media (max-width: 1024px) {
  .workspace, .workspace.collapsed { grid-template-columns: 1fr; max-width: 880px; }
  .dock { order: -1; }
}
/* 窄屏: 侧栏退为顶部横向导航 */
@media (max-width: 760px) {
  .app { grid-template-columns: 1fr; }
  .main { padding: 14px; }
}
</style>
