import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

// vitest.config.mtsでtest.globalsを有効にしていないため、
// @testing-library/reactの自動cleanup(afterEach)が暗黙には効かない。
// 明示的に登録し、テスト間でDOMがリークしないようにする。
afterEach(() => {
  cleanup();
});
