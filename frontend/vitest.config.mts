import path from "path";
import { fileURLToPath } from "url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const currentDir = path.dirname(fileURLToPath(import.meta.url));

/**
 * Phase 5Cで導入したVitest設定。
 *
 * 大きなfrontend test suite・E2E(Playwright等)は今回は導入せず、
 * 以下に絞って自動テストを書く(Implementation Plan参照):
 *   - static catalog integrity / relation lookup(純粋関数、jsdom不要)
 *   - useCriteriaSelectionフック(純粋ロジック)
 *   - SuggestPointsPanel等、少数のコンポーネントのRTLテスト
 * 実Gemini/Tavily APIは呼ばない(必ずmock/fakeを使う)。
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": currentDir,
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules", ".next"],
  },
});
