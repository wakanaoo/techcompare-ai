import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCriteriaSelection } from "@/hooks/useCriteriaSelection";
import { SuggestPointsPanel } from "./SuggestPointsPanel";

const suggestCriteriaMock = vi.fn();

vi.mock("@/lib/api", () => ({
  suggestCriteria: (...args: unknown[]) => suggestCriteriaMock(...args),
}));

function Harness({ goal = "SNS投稿を大量保存したい" }: { goal?: string }) {
  const criteria = useCriteriaSelection([]);
  return (
    <SuggestPointsPanel
      itemA="PostgreSQL"
      itemB="MongoDB"
      goal={goal}
      basePoints={["Query capability", "Schema flexibility", "Operations"]}
      criteria={criteria}
    />
  );
}

describe("SuggestPointsPanel", () => {
  beforeEach(() => {
    suggestCriteriaMock.mockReset();
  });

  it("disables Suggest Points and exposes the reason via a title tooltip when goal is empty", () => {
    render(<Harness goal="" />);

    const button = screen.getByRole("button", { name: "Suggest Points" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Use Caseを入力すると提案できます");
  });

  it("calls suggestCriteria with item_a/item_b/goal/existing_criteria=basePoints on click", async () => {
    suggestCriteriaMock.mockResolvedValue({ suggestions: [] });
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Suggest Points" }));

    await waitFor(() => expect(suggestCriteriaMock).toHaveBeenCalledTimes(1));
    expect(suggestCriteriaMock).toHaveBeenCalledWith({
      item_a: "PostgreSQL",
      item_b: "MongoDB",
      goal: "SNS投稿を大量保存したい",
      existing_criteria: ["Query capability", "Schema flexibility", "Operations"],
    });
  });

  it("shows a loading state while the request is in flight", async () => {
    let resolveFn: (value: { suggestions: never[] }) => void = () => {};
    suggestCriteriaMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFn = resolve;
        }),
    );
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Suggest Points" }));

    expect(screen.getByRole("button", { name: "Suggest Points" })).toBeDisabled();

    resolveFn({ suggestions: [] });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Suggest Points" })).not.toBeDisabled(),
    );
  });

  it("renders suggestions with name and reason on success", async () => {
    suggestCriteriaMock.mockResolvedValue({
      suggestions: [
        { name: "Query capability", reason: "既にBase Pointsにある(重複)" },
        { name: "Write throughput", reason: "SNS投稿の大量書き込みに直結するため" },
      ],
    });
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Suggest Points" }));

    await screen.findByRole("button", { name: "Write throughput" });
    expect(
      screen.getByText("SNS投稿の大量書き込みに直結するため"),
    ).toBeInTheDocument();
  });

  it("shows a generic user-facing error (no status code/provider detail) and allows manual retry on failure", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    suggestCriteriaMock.mockRejectedValueOnce(
      new Error(
        "比較ポイント候補の取得に失敗しました (LLM API呼び出しでエラーが発生しました(status: 503)。)",
      ),
    );
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Suggest Points" }));

    const retryButton = await screen.findByRole("button", { name: "Retry Suggest Points" });
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("提案を取得できませんでした。もう一度お試しください。");
    // status codeやprovider名などの技術的詳細はUIに出さない(consoleにのみ残す)。
    expect(alert.textContent).not.toMatch(/status|503|LLM API/);
    expect(consoleErrorSpy).toHaveBeenCalled();
    expect(retryButton).not.toBeDisabled();

    consoleErrorSpy.mockRestore();

    suggestCriteriaMock.mockResolvedValueOnce({
      suggestions: [{ name: "Write throughput", reason: "理由" }],
    });
    fireEvent.click(retryButton);

    await screen.findByRole("button", { name: "Write throughput" });
    expect(suggestCriteriaMock).toHaveBeenCalledTimes(2);
  });

  it("toggles a suggestion into the selection when its chip is clicked", async () => {
    suggestCriteriaMock.mockResolvedValue({
      suggestions: [{ name: "Write throughput", reason: "理由" }],
    });
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Suggest Points" }));
    const suggestionChip = await screen.findByRole("button", { name: "Write throughput" });

    expect(suggestionChip).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(suggestionChip);
    expect(suggestionChip).toHaveAttribute("aria-pressed", "true");
  });
});
