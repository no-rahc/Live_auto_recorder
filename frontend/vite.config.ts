import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/static/library/',
  build: {
    outDir: '../templates/static/library', emptyOutDir: true, sourcemap: false,
    rollupOptions: { input: 'src/main.tsx', output: {
      entryFileNames: 'library.js', chunkFileNames: 'chunks/[name]-[hash].js',
      assetFileNames: asset => asset.names?.some(name => name.endsWith('.css')) ? 'library.css' : 'assets/[name]-[hash][extname]',
    } },
  },
  test: { environment: 'jsdom', include: ['tests/**/*.test.ts', 'tests/**/*.test.tsx'], clearMocks: true },
});
