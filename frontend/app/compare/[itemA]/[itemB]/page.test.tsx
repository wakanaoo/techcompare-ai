import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompareSetupPage from "./page";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ itemA: "postgresql", itemB: "mongodb" }),
  useRouter: () => ({ push: pushMock }),
}));

const createResearchMock = vi.fn();
const suggestCriteriaMock = vi.fn();

vi.mock("@/lib/api", () => ({
  createResearch: (...args: unknown[]) => createResearchMock(...args),
  suggestCriteria: (...args: unknown[]) => suggestCriteriaMock(...args),
}));

describe("CompareSetupPage", () => {
  beforeEach(() => {
    pushMock.mockReset();
    createResearchMock.mockReset();
    suggestCriteriaMock.mockReset();
  });

  it("shows both technologies, their subcategories, and the relation summary", () => {
    render(<CompareSetupPage />);

    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("MongoDB")).toBeInTheDocument();
    expect(screen.getByText("HOW ARE THEY RELATED?")).toBeInTheDocument();
  });

  it("renders the pair's Base Points as chips", () => {
    render(<CompareSetupPage />);

    expect(screen.getByRole("button", { name: "Query capability" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Schema flexibility" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Operations" })).toBeInTheDocument();
  });

  it("dedupes a Base Point and a later custom entry with the same canonical key", () => {
    render(<CompareSetupPage />);

    fireEvent.click(screen.getByRole("button", { name: "Query capability" }));

    const customInput = screen.getByPlaceholderText("例:検索の柔軟性(Enterで追加)".replace(":", "："));
    fireEvent.change(customInput, { target: { value: "Query capability" } });
    fireEvent.click(screen.getByRole("button", { name: "追加" }));

    expect(screen.getByText("その項目はすでに追加されています")).toBeInTheDocument();
  });

  it("dedupes an AI suggestion against an already-selected Base Point by canonical key", async () => {
    suggestCriteriaMock.mockResolvedValue({
      suggestions: [{ name: "query capability", reason: "既にBase Pointsと重複" }],
    });
    render(<CompareSetupPage />);

    fireEvent.click(screen.getByRole("button", { name: "Query capability" }));
    fireEvent.change(screen.getByPlaceholderText("例: SNS投稿を大量保存したい"), {
      target: { value: "SNS投稿を大量保存したい" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Suggest Points" }));

    const suggestionChip = await screen.findByRole("button", { name: "query capability" });
    // "Query capability"(Base Point、既に選択中)と大文字小文字だけ異なる
    // "query capability"は同じcanonical keyなので、AI提案chipは最初から
    // 「選択済み」として表示される(クリックで別々に2件になることはない)。
    expect(suggestionChip).toHaveAttribute("aria-pressed", "true");
  });

  it("submits Start Research with the technology names, goal, and selected criteria", async () => {
    createResearchMock.mockResolvedValue({ id: 7 });
    render(<CompareSetupPage />);

    fireEvent.change(screen.getByPlaceholderText("例: SNS投稿を大量保存したい"), {
      target: { value: "SNS投稿を大量保存したい" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Query capability" }));
    fireEvent.click(screen.getByRole("button", { name: "Schema flexibility" }));

    fireEvent.click(screen.getByRole("button", { name: "Start Research" }));

    await waitFor(() => expect(createResearchMock).toHaveBeenCalledTimes(1));
    expect(createResearchMock).toHaveBeenCalledWith({
      item_a: "PostgreSQL",
      item_b: "MongoDB",
      goal: "SNS投稿を大量保存したい",
      criteria: ["Query capability", "Schema flexibility"],
    });
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/research/7"));
  });

  it("shows a short Japanese description for a Base Point via InfoTooltip on focus", () => {
    render(<CompareSetupPage />);

    const infoTrigger = screen.getByRole("button", { name: "Query capabilityの説明" });
    fireEvent.focus(infoTrigger);

    expect(
      screen.getByText("データの検索・集計をどれだけ柔軟に行えるか。"),
    ).toBeInTheDocument();
  });

  it("fills this pair's curated Use Case Example when the Example action is clicked", () => {
    render(<CompareSetupPage />);

    fireEvent.click(screen.getByRole("button", { name: "↗ Example" }));

    expect(screen.getByPlaceholderText("例: SNS投稿を大量保存したい")).toHaveValue(
      "プロトタイプのSNSアプリで投稿を大量保存したい",
    );
  });

  it("shows a manually-added custom criterion as a removable chip", () => {
    render(<CompareSetupPage />);

    const customInput = screen.getByPlaceholderText("例:検索の柔軟性(Enterで追加)".replace(":", "："));
    fireEvent.change(customInput, { target: { value: "検索の柔軟性" } });
    fireEvent.click(screen.getByRole("button", { name: "追加" }));

    expect(screen.getByRole("button", { name: "検索の柔軟性 ✕" })).toBeInTheDocument();
  });

  it("blocks Start Research when no criteria are selected", () => {
    render(<CompareSetupPage />);

    fireEvent.change(screen.getByPlaceholderText("例: SNS投稿を大量保存したい"), {
      target: { value: "SNS投稿を大量保存したい" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start Research" }));

    expect(screen.getByText("項目を最低1個選んでください")).toBeInTheDocument();
    expect(createResearchMock).not.toHaveBeenCalled();
  });
});
