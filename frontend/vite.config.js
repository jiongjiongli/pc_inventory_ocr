import { defineConfig } from 'vite';
export default defineConfig({server: {proxy: {'/api': 'http://127.0.0.1:5000', '/photos': 'http://127.0.0.1:5000', '/pcs': 'http://127.0.0.1:5000'}}});
