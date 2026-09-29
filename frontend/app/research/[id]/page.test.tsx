import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ResearchProgressPage from "./page";
import type { Research } from "@/lib/api";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "1" }),
  useRouter: () => ({ push: pushMock }),
}));

const getResearchMock = vi.fn();
const createResearchMock = vi.fn();

vi.mock("@/lib/api", () => ({
  getResearch: (...args: unknown[]) => getResearchMock(...args),
  createResearch: (...args: unknown[]) => createResearchMock(...args),
}));

function baseResearch(overrides: Partial<Research>): Research {
  return {
    id: 1,
    item_a: "FastAPI",
    item_b: "Django",
    goal: "AIアプリのバックエンド",
    criteria: ["Development speed"],
    status: "pending",
    error_message: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

/**
 * Research Progress(Phase 5C Finishing)の簡素化された表示のregression。
 * backendが実際に返す4状態(pending/researching/completed/failed)だけを
 * 反映し、架空の中間ステップ(旧「受付/処理中/完了」の3ノード)を
 * 表示しないことを確認する。
 */
describe("ResearchProgressPage", () => {
  beforeEach(() => {
    pushMock.mockReset();
    getResearchMock.mockReset();
    createResearchMock.mockReset();
  });

  it("shows a calm 'Researching…' indicator while pending/researching, without a fabricated step checklist", async () => {
    getResearchMock.mockResolvedValue(baseResearch({ status: "researching" }));
    render(<ResearchProgressPage />);

    await waitFor(() => expect(screen.getByText("Researching…")).toBeInTheDocument());

    // 旧StatusTimelineの固定ラベル(受付/完了)は、architectureのcommentどおり
    // 実際のstatusに存在しない中間状態なので、もう表示されない。
    expect(screen.queryByText("受付")).not.toBeInTheDocument();
    expect(screen.queryByText("完了")).not.toBeInTheDocument();
  });

  it("shows the item_a/item_b converging-dot motion as a decorative element while active", async () => {
    getResearchMock.mockResolvedValue(baseResearch({ status: "researching" }));
    render(<ResearchProgressPage />);

    await waitFor(() => expect(screen.getByText("Researching…")).toBeInTheDocument());

    expect(screen.getByText("FastAPI")).toBeInTheDocument();
    expect(screen.getByText("Django")).toBeInTheDocument();
    // "Research Progress"という大見出しはもう表示しない。
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });

  it("shows the retry UI on failure, without the 'Researching…' indicator", async () => {
    getResearchMock.mockResolvedValue(
      baseResearch({ status: "failed", error_message: "unexpected_error" }),
    );
    render(<ResearchProgressPage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "同じ条件でもう一度試す" })).toBeInTheDocument(),
    );
    expect(screen.queryByText("Researching…")).not.toBeInTheDocument();
  });

  it("redirects to the result page once completed", async () => {
    getResearchMock.mockResolvedValue(baseResearch({ status: "completed" }));
    render(<ResearchProgressPage />);

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/research/1/result"));
  });
});
