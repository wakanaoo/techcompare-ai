/**
 * Backend(FastAPI)を呼び出すための最小限のAPIクライアント。
 *
 * Phase 1で使うのは POST /research と GET /research/{id} のみ。
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type ResearchStatus = "pending" | "researching" | "completed" | "failed";

export interface Research {
  id: number;
  item_a: string;
  item_b: string;
  goal: string;
  status: ResearchStatus;
  created_at: string;
  updated_at: string;
}

export interface ResearchCreateInput {
  item_a: string;
  item_b: string;
  goal: string;
}

export async function createResearch(
  input: ResearchCreateInput,
): Promise<Research> {
  const response = await fetch(`${API_BASE_URL}/research`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  if (!response.ok) {
    throw new Error(`Researchの作成に失敗しました (status: ${response.status})`);
  }

  return response.json();
}

export async function getResearch(id: string): Promise<Research> {
  const response = await fetch(`${API_BASE_URL}/research/${id}`);

  if (response.status === 404) {
    throw new Error("指定されたResearchが見つかりません");
  }
  if (!response.ok) {
    throw new Error(`Researchの取得に失敗しました (status: ${response.status})`);
  }

  return response.json();
}
