import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CriterionChip } from "./CriterionChip";

describe("CriterionChip", () => {
  it("renders a plain chip (no InfoTooltip) when no description is given", () => {
    render(<CriterionChip label="Custom point" selected={false} onToggle={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Custom point" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /の説明$/ })).not.toBeInTheDocument();
  });

  it("toggles selection when the chip itself is clicked", async () => {
    const onToggle = vi.fn();
    render(
      <CriterionChip
        label="Learning curve"
        selected={false}
        onToggle={onToggle}
        description="習得のしやすさ。"
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Learning curve" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("clicking the InfoTooltip trigger does not toggle selection (sibling elements, not nested)", async () => {
    const onToggle = vi.fn();
    render(
      <CriterionChip
        label="Learning curve"
        selected={false}
        onToggle={onToggle}
        description="習得のしやすさ。"
      />,
    );

    const infoTrigger = screen.getByRole("button", { name: "Learning curveの説明" });
    await userEvent.click(infoTrigger);
    expect(onToggle).not.toHaveBeenCalled();

    // hoverで説明が出ることも合わせて確認する(InfoTooltip単体のテストと重複しすぎない範囲で)。
    await userEvent.hover(infoTrigger);
    expect(screen.getByRole("tooltip")).toHaveTextContent("習得のしやすさ。");
  });
});
