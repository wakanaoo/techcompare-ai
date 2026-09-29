import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import NewResearchPage from "./page";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const createResearchMock = vi.fn();
const suggestCriteriaMock = vi.fn();

vi.mock("@/lib/api", () => ({
  createResearch: (...args: unknown[]) => createResearchMock(...args),
  suggestCriteria: (...args: unknown[]) => suggestCriteriaMock(...args),
}));

/** Compareボタンをクリックしてinline展開した状態にする(既存フォーム操作テスト用)。 */
function expandCompare() {
  fireEvent.click(screen.getByRole("button", { name: /Compare/ }));
}

/**
 * Direct Compare(Home)のregressionテスト(Phase 5C Finishing 追補v4)。
 *
 * Home初期状態はLearn(旧Explore)/Compareという2つの同格の入口だけを見せ、
 * Compareのフォームはクリックするまでinline展開しない。展開後の挙動
 * (Base Points・Suggest Points・custom追加・Start Research)は従来どおり。
 */
describe("NewResearchPage (Direct Compare)", () => {
  beforeEach(() => {
    pushMock.mockReset();
    createResearchMock.mockReset();
    suggestCriteriaMock.mockReset();
  });

  it("shows only the hero and two equally-weighted entries initially, with the Compare form collapsed", () => {
    render(<NewResearchPage />);

    expect(screen.getByText("Explore technologies. Compare what fits.")).toBeInTheDocument();

    const learnLink = screen.getByRole("link", { name: /Learn/ });
    expect(learnLink).toHaveAttribute("href", "/explore");

    const compareToggle = screen.getByRole("button", { name: /Compare/ });
    expect(compareToggle).toHaveAttribute("aria-expanded", "false");
    expect(compareToggle).toHaveAttribute("aria-controls", "compare-panel");

    const panel = document.getElementById("compare-panel");
    expect(panel).not.toBeNull();
    expect(panel).toHaveAttribute("inert");
  });

  it("expands the Compare form inline (no navigation) when the Compare entry is clicked", () => {
    render(<NewResearchPage />);

    expandCompare();

    const compareToggle = screen.getByRole("button", { name: /Compare/ });
    expect(compareToggle).toHaveAttribute("aria-expanded", "true");

    const panel = document.getElementById("compare-panel");
    expect(panel).not.toHaveAttribute("inert");
    expect(screen.getByPlaceholderText("例: FastAPI")).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("uses the same 'What are you building?' wording as Compare Setup", () => {
    render(<NewResearchPage />);
    expandCompare();
    expect(screen.getByText("What are you building?")).toBeInTheDocument();
  });

  it("shows a compact 'Base Points · N/M' label and pre-selects the default chips using English labels", () => {
    render(<NewResearchPage />);
    expandCompare();

    expect(screen.getByText("Base Points · 3/5")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "Development speed" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "AI app fit" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Learning curve" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Performance" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("shows a short Japanese description for a Base Point via InfoTooltip on focus", () => {
    render(<NewResearchPage />);
    expandCompare();

    const infoTrigger = screen.getByRole("button", { name: "Learning curveの説明" });
    fireEvent.focus(infoTrigger);

    expect(
      screen.getByText("習得のしやすさ。ドキュメントの分かりやすさや、必要な前提知識の少なさ。"),
    ).toBeInTheDocument();
  });

  it("toggles a candidate chip on and off", () => {
    render(<NewResearchPage />);
    expandCompare();
    const costChip = screen.getByRole("button", { name: "Cost" });

    fireEvent.click(costChip);
    expect(costChip).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(costChip);
    expect(costChip).toHaveAttribute("aria-pressed", "false");
  });

  it("adds a custom criterion via the text input", () => {
    render(<NewResearchPage />);
    expandCompare();
    const input = screen.getByPlaceholderText("追加する項目");

    fireEvent.change(input, { target: { value: "検索の柔軟性" } });
    fireEvent.click(screen.getByRole("button", { name: "追加" }));

    expect(screen.getByRole("button", { name: "検索の柔軟性 ✕" })).toBeInTheDocument();
  });

  it("shows an error when adding a duplicate custom criterion (case-insensitive)", () => {
    render(<NewResearchPage />);
    expandCompare();
    const input = screen.getByPlaceholderText("追加する項目");

    fireEvent.change(input, { target: { value: "Cost" } });
    fireEvent.click(screen.getByRole("button", { name: "追加" }));
    fireEvent.change(input, { target: { value: "cost" } });
    fireEvent.click(screen.getByRole("button", { name: "追加" }));

    expect(screen.getByText("その項目はすでに追加されています")).toBeInTheDocument();
  });

  it("offers Suggest Points (reusing POST /suggest-criteria) directly from the Direct Compare form", async () => {
    suggestCriteriaMock.mockResolvedValue({
      suggestions: [{ name: "Write throughput", reason: "大量書き込みが多いため" }],
    });
    render(<NewResearchPage />);
    expandCompare();

    fireEvent.change(screen.getByPlaceholderText("例: FastAPI"), {
      target: { value: "FastAPI" },
    });
    fireEvent.change(screen.getByPlaceholderText("例: Django"), {
      target: { value: "Django" },
    });
    fireEvent.change(
      screen.getByPlaceholderText("例: AIアプリのバックエンドとして比較したい"),
      { target: { value: "AIアプリのバックエンド" } },
    );

    fireEvent.click(screen.getByRole("button", { name: "Suggest Points" }));

    await waitFor(() => expect(suggestCriteriaMock).toHaveBeenCalledTimes(1));
    expect(suggestCriteriaMock).toHaveBeenCalledWith({
      item_a: "FastAPI",
      item_b: "Django",
      goal: "AIアプリのバックエンド",
      existing_criteria: [
        "Learning curve",
        "Development speed",
        "AI app fit",
        "Performance",
        "Async support",
        "Type safety",
        "Deployability",
        "Ecosystem",
        "Operability",
        "Cost",
      ],
    });

    const suggestionChip = await screen.findByRole("button", { name: "Write throughput" });
    fireEvent.click(suggestionChip);
    expect(suggestionChip).toHaveAttribute("aria-pressed", "true");
  });

  it("submits with the entered fields and default criteria, then navigates to the progress page", async () => {
    createResearchMock.mockResolvedValue({ id: 42 });
    render(<NewResearchPage />);
    expandCompare();

    fireEvent.change(screen.getByPlaceholderText("例: FastAPI"), {
      target: { value: "FastAPI" },
    });
    fireEvent.change(screen.getByPlaceholderText("例: Django"), {
      target: { value: "Django" },
    });
    fireEvent.change(
      screen.getByPlaceholderText("例: AIアプリのバックエンドとして比較したい"),
      { target: { value: "AIアプリのバックエンド" } },
    );

    fireEvent.click(screen.getByRole("button", { name: "Start Research" }));

    await waitFor(() => expect(createResearchMock).toHaveBeenCalledTimes(1));
    expect(createResearchMock).toHaveBeenCalledWith({
      item_a: "FastAPI",
      item_b: "Django",
      goal: "AIアプリのバックエンド",
      criteria: ["Development speed", "AI app fit", "Learning curve"],
    });
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/research/42"));
  });

  it("cycles through curated Technology A/B pairs on each 'Example comparison' click", () => {
    render(<NewResearchPage />);
    expandCompare();

    const itemAInput = screen.getByPlaceholderText("例: FastAPI");
    const itemBInput = screen.getByPlaceholderText("例: Django");
    const exampleComparisonButton = screen.getByRole("button", { name: "↗ Example comparison" });

    fireEvent.click(exampleComparisonButton); // 1件目(先頭)を採用
    expect(itemAInput).toHaveValue("FastAPI");
    expect(itemBInput).toHaveValue("Django");

    fireEvent.click(exampleComparisonButton); // 2件目へ
    expect(itemAInput).toHaveValue("PostgreSQL");
    expect(itemBInput).toHaveValue("MongoDB");

    fireEvent.click(exampleComparisonButton); // 3件目へ
    expect(itemAInput).toHaveValue("PostgreSQL");
    expect(itemBInput).toHaveValue("MySQL");
  });

  it("does not overwrite Technology A/B via 'Example comparison' once the user has typed their own values", () => {
    render(<NewResearchPage />);
    expandCompare();

    const itemAInput = screen.getByPlaceholderText("例: FastAPI");
    const itemBInput = screen.getByPlaceholderText("例: Django");

    fireEvent.change(itemAInput, { target: { value: "Rust" } });
    fireEvent.change(itemBInput, { target: { value: "Go" } });

    fireEvent.click(screen.getByRole("button", { name: "↗ Example comparison" }));

    expect(itemAInput).toHaveValue("Rust");
    expect(itemBInput).toHaveValue("Go");
  });

  it("does not overwrite Technology A/B when only one of the two was manually edited", () => {
    render(<NewResearchPage />);
    expandCompare();

    const itemAInput = screen.getByPlaceholderText("例: FastAPI");
    const itemBInput = screen.getByPlaceholderText("例: Django");
    const exampleComparisonButton = screen.getByRole("button", { name: "↗ Example comparison" });

    fireEvent.click(exampleComparisonButton); // FastAPI / Django
    fireEvent.change(itemBInput, { target: { value: "Flask" } }); // Bだけ自分で書き換える

    fireEvent.click(exampleComparisonButton); // 片方だけ一致でも進めない(安全策)

    expect(itemAInput).toHaveValue("FastAPI");
    expect(itemBInput).toHaveValue("Flask");
  });

  it("selecting an Example comparison pair also updates the 'What are you building?' Example hint", () => {
    render(<NewResearchPage />);
    expandCompare();

    fireEvent.click(screen.getByRole("button", { name: "↗ Example comparison" })); // FastAPI / Django

    fireEvent.click(screen.getByRole("button", { name: "↗ Example" }));
    expect(
      screen.getByPlaceholderText("例: AIアプリのバックエンドとして比較したい"),
    ).toHaveValue("個人開発でAIアプリのバックエンドAPIを素早く作りたい");
  });

  it("shows Technology-pair-specific Use Case Examples once both names match the catalog", () => {
    render(<NewResearchPage />);
    expandCompare();

    fireEvent.change(screen.getByPlaceholderText("例: FastAPI"), {
      target: { value: "PostgreSQL" },
    });
    fireEvent.change(screen.getByPlaceholderText("例: Django"), {
      target: { value: "MongoDB" },
    });

    fireEvent.click(screen.getByRole("button", { name: "↗ Example" }));
    expect(
      screen.getByPlaceholderText("例: AIアプリのバックエンドとして比較したい"),
    ).toHaveValue("プロトタイプのSNSアプリで投稿を大量保存したい");
  });
});
