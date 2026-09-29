import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InfoTooltip } from "./InfoTooltip";

/**
 * jsdomは`window.matchMedia`を実装していないため、InfoTooltip側は
 * `!window.matchMedia`をtouch判定のfallbackとして扱う(=デフォルトでは
 * "hoverあり(PC)"として振る舞う)。タッチ端末相当の挙動を確認するテストだけ、
 * `(hover: none)`にマッチするmatchMediaをmockする。
 */
function mockMatchMedia(matchesHoverNone: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: query === "(hover: none)" ? matchesHoverNone : false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

/**
 * パネルはfade/translateのtransitionを両方向で効かせるため常時DOMに
 * マウントしたままにし、表示状態は`--visible` classで切り替える
 * (`components/InfoTooltip.tsx`参照)。DOM上の有無ではなくこのclassで判定する。
 */
function isPanelVisible(panel: HTMLElement): boolean {
  return panel.classList.contains("info-tooltip__panel--visible");
}

describe("InfoTooltip", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("hides the description by default", () => {
    render(<InfoTooltip triggerLabel="Learning curveの説明" description="習得のしやすさ。" />);
    expect(isPanelVisible(screen.getByRole("tooltip", { hidden: true }))).toBe(false);
  });

  it("shows the description on hover and hides it on mouse leave (desktop)", async () => {
    render(<InfoTooltip triggerLabel="Learning curveの説明" description="習得のしやすさ。" />);
    const trigger = screen.getByRole("button", { name: "Learning curveの説明" });
    const panel = screen.getByRole("tooltip", { hidden: true });

    await userEvent.hover(trigger);
    expect(isPanelVisible(panel)).toBe(true);
    expect(panel).toHaveTextContent("習得のしやすさ。");

    await userEvent.unhover(trigger);
    expect(isPanelVisible(panel)).toBe(false);
  });

  it("shows the description on keyboard focus and hides it on blur (keyboard accessibility)", () => {
    render(<InfoTooltip triggerLabel="Learning curveの説明" description="習得のしやすさ。" />);
    const trigger = screen.getByRole("button", { name: "Learning curveの説明" });
    const panel = screen.getByRole("tooltip", { hidden: true });

    fireEvent.focus(trigger);
    expect(isPanelVisible(panel)).toBe(true);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    fireEvent.blur(trigger);
    expect(isPanelVisible(panel)).toBe(false);
  });

  it("closes on Escape while open", () => {
    render(<InfoTooltip triggerLabel="Learning curveの説明" description="習得のしやすさ。" />);
    const trigger = screen.getByRole("button", { name: "Learning curveの説明" });
    const panel = screen.getByRole("tooltip", { hidden: true });

    fireEvent.focus(trigger);
    expect(isPanelVisible(panel)).toBe(true);

    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(isPanelVisible(panel)).toBe(false);
  });

  it("on touch devices, ignores hover and toggles the description via tap (click)", async () => {
    mockMatchMedia(true);
    render(<InfoTooltip triggerLabel="Learning curveの説明" description="習得のしやすさ。" />);
    const trigger = screen.getByRole("button", { name: "Learning curveの説明" });
    const panel = screen.getByRole("tooltip", { hidden: true });

    await userEvent.hover(trigger);
    expect(isPanelVisible(panel)).toBe(false);

    await userEvent.click(trigger);
    expect(isPanelVisible(panel)).toBe(true);

    await userEvent.click(trigger);
    expect(isPanelVisible(panel)).toBe(false);
  });
});
