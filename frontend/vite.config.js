import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'StarzChat',
        short_name: 'StarzChat',
        description: 'Self-deleting student chat',
        display: 'standalone',
        background_color: '#0b141a',
        theme_color: '#0b141a',
        icons: [
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
        ],
      },
      workbox: { navigateFallbackDenylist: [/^\/api/, /^\/socket.io/] },
    }),
  ],
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/setupTests.js'] },
});
