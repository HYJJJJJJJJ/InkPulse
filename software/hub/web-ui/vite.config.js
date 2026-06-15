import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 产物输出到 dist/, 由 FastAPI StaticFiles 挂载到 /
// 开发时 vite dev server 反代后端(默认 8080), 这样 /api /frame /preview.png /photos 直连 hub
const HUB = process.env.INKPULSE_HUB || 'http://127.0.0.1:8080'
const proxy = Object.fromEntries(
  ['/api', '/frame', '/preview.png', '/photos'].map((p) => [p, { target: HUB, changeOrigin: true }])
)

export default defineConfig({
  plugins: [vue()],
  base: './',
  build: { outDir: 'dist', emptyOutDir: true },
  server: { proxy },
})
