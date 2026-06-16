<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { store, toast } from '../store.js'
import { api } from '../api.js'

const NAMES = { dash: '仪表盘', photo: '相框', usage: '用量', todo: '待办', clock: '摆钟', split: '双栏' }

// ---- 布局选择 ----
const layouts = ref([])
const current = ref('')
async function loadConfig() {
  const c = await api.get('/api/config')
  layouts.value = c.layouts; current.value = c.layout_name
}
async function setLayout(k) {
  try { await api.post('/api/config', { layout_name: k }); current.value = k }
  catch (e) { toast('切换失败: ' + e.message) }
}

// ---- 布局编辑器 ----
const grid = ref({ cols: 8, rows: 6 })
const widgets = ref([])               // widget 目录
const builtins = ref(new Set())
const store_layouts = ref({})         // name -> {placements, builtin}
const edName = ref('')
const placements = ref([])
const sel = ref(null)                 // {c0,r0,c1,r1}
const anchor = ref(null)
const edWidget = ref('')
const params = ref({})                // 当前 widget 参数表单值

async function loadStore() {
  const d = await api.get('/api/layouts')
  grid.value = d.grid
  widgets.value = d.widgets
  store_layouts.value = d.layouts
  builtins.value = new Set(Object.entries(d.layouts).filter(([, v]) => v.builtin).map(([k]) => k))
  if (!edName.value) edName.value = Object.keys(d.layouts)[0] || ''
  if (!edWidget.value && widgets.value.length) edWidget.value = widgets.value[0].name
  pickLayout(edName.value)
}
function pickLayout(name) {
  edName.value = name
  const lay = store_layouts.value[name] || {}
  placements.value = JSON.parse(JSON.stringify(lay.placements || []))
  sel.value = null; anchor.value = null
}

const curWidget = computed(() => widgets.value.find((w) => w.name === edWidget.value))
watch(edWidget, () => {
  const w = curWidget.value
  const p = {}
  if (w) for (const pr of w.params || []) p[pr.key] = pr.default ?? ''
  params.value = p
})

// 占用映射: "c,r" -> placement index
const occ = computed(() => {
  const m = {}
  placements.value.forEach((p, i) => {
    for (let c = p.col; c < p.col + p.colspan; c++)
      for (let r = p.row; r < p.row + p.rowspan; r++) m[c + ',' + r] = i
  })
  return m
})
// 背景格子只负责框选; 已放置的 widget 单独渲染成整块色块, 不在每格重复标签
const baseCells = computed(() => {
  const out = []
  for (let r = 0; r < grid.value.rows; r++)
    for (let c = 0; c < grid.value.cols; c++) {
      const inSel = sel.value && c >= sel.value.c0 && c <= sel.value.c1 && r >= sel.value.r0 && r <= sel.value.r1
      out.push({ c, r, inSel, occupied: occ.value[c + ',' + r] !== undefined })
    }
  return out
})
function widgetLabel(name) {
  const w = widgets.value.find((x) => x.name === name)
  return w ? w.label : name
}
const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${grid.value.cols}, 1fr)`,
  gridTemplateRows: `repeat(${grid.value.rows}, 1fr)`,
  // 编辑框形状跟随真机网格(7.5寸横版 8x6 / 4.2寸竖版 4x8), 不再写死 5:3
  aspectRatio: `${grid.value.cols} / ${grid.value.rows}`,
}))
function cellStyle(cell) { return { gridColumn: `${cell.c + 1}`, gridRow: `${cell.r + 1}` } }
function blockStyle(p) {
  return { gridColumn: `${p.col + 1} / span ${p.colspan}`, gridRow: `${p.row + 1} / span ${p.rowspan}` }
}
const selStyle = computed(() => {
  const s = sel.value
  if (!s) return null
  return { gridColumn: `${s.c0 + 1} / span ${s.c1 - s.c0 + 1}`, gridRow: `${s.r0 + 1} / span ${s.r1 - s.r0 + 1}` }
})
function clickEmpty(cell) {
  if (cell.occupied) return
  if (!anchor.value) { anchor.value = { c: cell.c, r: cell.r }; sel.value = { c0: cell.c, r0: cell.r, c1: cell.c, r1: cell.r } }
  else {
    sel.value = {
      c0: Math.min(anchor.value.c, cell.c), r0: Math.min(anchor.value.r, cell.r),
      c1: Math.max(anchor.value.c, cell.c), r1: Math.max(anchor.value.r, cell.r),
    }
    anchor.value = null
  }
}
function removeAt(i) { placements.value.splice(i, 1) }
function place() {
  if (!sel.value) { toast('先在网格里框选一块区域'); return }
  placements.value.push({
    widget: edWidget.value, col: sel.value.c0, row: sel.value.r0,
    colspan: sel.value.c1 - sel.value.c0 + 1, rowspan: sel.value.r1 - sel.value.r0 + 1,
    params: { ...params.value },
  })
  sel.value = null; anchor.value = null
}
async function save() {
  let name = edName.value
  if (builtins.value.has(name)) {
    name = prompt('内置布局只读, 另存为新布局名:', name + '-我的')
    if (!name) return
    edName.value = name
  }
  try {
    await api.put('/api/layouts/' + encodeURIComponent(name), { placements: placements.value })
    toast('已保存。切到该布局并刷新屏幕即可上屏')
    await loadStore(); await loadConfig()
  } catch (e) { toast('保存失败: ' + e.message) }
}
function newLayout() {
  const name = prompt('新布局名'); if (!name) return
  edName.value = name; placements.value = []; sel.value = null; anchor.value = null
  if (!store_layouts.value[name]) store_layouts.value[name] = { placements: [] }
}
async function delLayout() {
  if (!edName.value) return
  try { await api.del('/api/layouts/' + encodeURIComponent(edName.value)); await loadStore(); await loadConfig() }
  catch (e) { toast(e.message) }
}

watch(() => store.syncToken, () => { loadConfig() })
onMounted(async () => { await loadConfig(); await loadStore() })
</script>

<template>
  <div class="card">
    <h2>布局</h2>
    <div class="layouts">
      <label v-for="k in layouts" :key="k" class="lay" :class="{ sel: k === current }" @click="setLayout(k)">
        <div class="nm">{{ NAMES[k] || k }}</div><small>{{ k }}</small>
      </label>
    </div>
  </div>

  <div class="card">
    <h2>
      布局编辑器
      <span class="tools">
        <select v-model="edName" @change="pickLayout(edName)">
          <option v-for="n in Object.keys(store_layouts)" :key="n" :value="n">{{ n }}</option>
        </select>
        <button class="ghost sm" @click="newLayout">新建</button>
        <button class="ghost sm" @click="delLayout">删除</button>
      </span>
    </h2>

    <div class="edgrid" :style="gridStyle">
      <div
        v-for="cell in baseCells" :key="cell.c + '-' + cell.r"
        class="gcell" :class="{ insel: cell.inSel, occ: cell.occupied }"
        :style="cellStyle(cell)"
        @click="clickEmpty(cell)"></div>
      <div
        v-for="(p, i) in placements" :key="'b' + i"
        class="block" :style="blockStyle(p)">
        <span class="blabel">{{ widgetLabel(p.widget) }}</span>
        <button class="bdel" title="删除" @click.stop="removeAt(i)">×</button>
      </div>
      <div v-if="selStyle" class="selbox" :style="selStyle"></div>
    </div>

    <div class="picker">
      <label class="lb">放入区域</label>
      <select v-model="edWidget" style="flex:1">
        <option v-for="w in widgets" :key="w.name" :value="w.name">{{ w.label }}</option>
      </select>
      <button class="accent" :disabled="!selStyle" @click="place">放入选区</button>
    </div>

    <div v-if="curWidget && curWidget.params && curWidget.params.length">
      <div v-for="p in curWidget.params" :key="p.key" class="row">
        <label class="lb">{{ p.label }}</label>
        <select v-if="p.type === 'select'" v-model="params[p.key]" style="flex:1">
          <option v-for="o in (p.options || [])" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <input v-else v-model="params[p.key]" :type="p.type === 'date' ? 'date' : (p.type === 'number' ? 'number' : 'text')" />
      </div>
    </div>

    <p class="hint">点空格起点、再点终点框出矩形 → 选 widget（填参数）→「放入选区」。已放置的色块悬停点 <b>×</b> 删除。改完点「保存布局」。内置布局只读, 改动会提示另存为新布局。</p>
    <button class="accent" style="margin-top:6px" @click="save">保存布局</button>
  </div>
</template>

<style scoped>
.layouts { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px; }
.lay { border: 2px solid var(--line); border-radius: 10px; padding: 12px; text-align: center; cursor: pointer; background: var(--paper); }
.lay:hover { border-color: var(--line-strong); }
.lay.sel { border-color: var(--accent); background: var(--accent-soft); }
.lay .nm { font-weight: 600; margin-bottom: 2px; }
.tools { display: flex; gap: 6px; align-items: center; }

/* 编辑网格: 空格淡雅虚线, widget 渲染成整块色块, 框选红框 */
.edgrid {
  display: grid; gap: 5px; padding: 6px;
  background: var(--paper); border: 1px solid var(--line-strong); border-radius: 12px;
  box-shadow: inset 0 1px 3px rgba(40,34,24,.05);   /* 宽高比由 gridStyle 动态绑定 */
}
.gcell {
  border: 1px dashed var(--line-strong); border-radius: 6px; background: transparent;
  cursor: crosshair; transition: background .12s, border-color .12s;
}
.gcell:hover { background: var(--accent-soft); border-color: var(--accent); }
.gcell.occ { pointer-events: none; border-color: transparent; }
.gcell.insel { background: #fcf3c6; border: 1px solid #e3c000; }
.block {
  position: relative; display: flex; align-items: center; justify-content: center;
  background: var(--ink); color: var(--paper-raised); border-radius: 8px;
  box-shadow: var(--shadow); overflow: hidden; cursor: default;
}
.block::before {   /* 左侧朱红脊, 呼应三色屏 */
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--accent);
}
.blabel { font-size: 12.5px; font-weight: 600; letter-spacing: .02em; padding: 2px 8px; text-align: center; }
.bdel {
  position: absolute; top: 4px; right: 4px; width: 19px; height: 19px; padding: 0;
  display: flex; align-items: center; justify-content: center; line-height: 1;
  font-size: 13px; border-radius: 6px; opacity: 0;
  background: var(--accent); border: 0; color: #fff; transition: opacity .12s;
}
.block:hover .bdel { opacity: 1; }
.selbox {
  pointer-events: none; border: 2px solid var(--accent); border-radius: 8px;
  background: rgba(192, 57, 43, .08);
}
.picker { display: flex; align-items: center; gap: 10px; margin-top: 14px; }
.lb { width: 84px; font-size: 14px; color: var(--ink-soft); flex: 0 0 auto; }
</style>
