import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import TechnologyDetailPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "postgresql" }),
}));

/**
 * Technology navigationの軽い検証(Implementation Plan: 「重要なlink/href
 * の検証程度で十分」)。ページ全体の見た目や状態遷移の網羅までは行わない。
 */
describe("TechnologyDetailPage", () => {
  it("links Common Comparisons to Compare Setup with item_a=current, item_b=target", () => {
    render(<TechnologyDetailPage />);

    const mongoLink = screen.getByRole("link", { name: "MongoDB" });
    expect(mongoLink).toHaveAttribute("href", "/compare/postgresql/mongodb");

    const sqliteLink = screen.getByRole("link", { name: "SQLite" });
    expect(sqliteLink).toHaveAttribute("href", "/compare/postgresql/sqlite");
  });

  it("links Related Technologies to their own Technology Detail page, not Compare Setup", () => {
    render(<TechnologyDetailPage />);

    const fastapiLink = screen.getByRole("link", { name: "FastAPI" });
    expect(fastapiLink).toHaveAttribute("href", "/explore/technology/fastapi");
  });

  it("links back to the parent category", () => {
    render(<TechnologyDetailPage />);

    expect(screen.getByRole("link", { name: "← Data" })).toHaveAttribute(
      "href",
      "/explore/data",
    );
  });

  it("shows a concept's explanation via InfoTooltip on focus, without navigating (keyboard accessible)", () => {
    render(<TechnologyDetailPage />);

    const trigger = screen.getByRole("button", { name: "SQLの説明" });
    // fade transitionのため常時DOMにはマウントされているが、表示状態は
    // `--visible` classで切り替わる(InfoTooltip.test.tsx参照)。
    const panel = screen.getByText(/Relational Databaseに対して/);
    expect(panel).not.toHaveClass("info-tooltip__panel--visible");

    fireEvent.focus(trigger);

    expect(panel).toHaveClass("info-tooltip__panel--visible");
  });
});
