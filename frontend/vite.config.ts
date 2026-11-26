import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_PROXY_TARGET || process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    build: {
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom', 'zustand'],
            charts: ['recharts'],
            markdown: ['react-markdown', 'rehype-raw', 'rehype-sanitize', 'dompurify'],
            mindmap: ['markmap-lib', 'markmap-view'],
          },
        },
      },
    },
    server: {
      port: 5173,
      strictPort: true,
      watch: {
        // 忽略原子保存产生的临时文件/目录。
        //
        // 真实故障：编辑器（VS Code、以及任何走"写临时文件再改名"的保存方式）
        // 会在目标文件旁边建 `.文件名.<pid>.<uuid>.tmpdir/文件名.tmp`。Vite 的
        // 文件监听会去 watch 这个目录里的临时文件，而 Windows 上它当时正被锁住，
        // 于是抛出 `EBUSY: resource busy or locked`，**整个 dev server 直接退出**。
        // 表现就是：改了代码、刷新浏览器却永远看不到变化（服务已经死了）。
        ignored: [
          '**/*.tmpdir/**',
          '**/.*.tmpdir/**',
          '**/*.tmp',
          '**/.*.tmp',
          '**/vite.config.ts.timestamp-*',
        ],
      },
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/output': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  }
})