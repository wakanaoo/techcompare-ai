/**
 * Backend(FastAPI)を呼び出すための最小限のAPIクライアント。
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type ResearchStatus = "pending" | "researching" | "completed" | "failed";
export type Winner = "item_a" | "item_b" | "tie";

export interface Research {
  id: number;
  item_a: string;
  item_b: string;
  goal: string;
  criteria: string[];
  status: ResearchStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResearchCreateInput {
  item_a: string;
  item_b: string;
  goal: string;
  criteria: string[];
}

export interface Recommendation {
  winner: Winner;
  summary: string;
  reason: string;
}

export interface ComparisonRow {
  criterion: string;
  criterion_label: string;
  item_a_summary: string;
  item_b_summary: string;
  item_a_score: number;
  item_b_score: number;
  winner: Winner;
}

export interface ResearchResult {
  research_id: number;
  item_a: string;
  item_b: string;
  goal: string;
  recommendation: Recommendation;
  comparisons: ComparisonRow[];
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

export async function getResearchResult(id: string): Promise<ResearchResult> {
  const response = await fetch(`${API_BASE_URL}/research/${id}/result`);

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail ?? `status: ${response.status}`;
    throw new Error(`比較結果の取得に失敗しました (${detail})`);
  }

  return response.json();
}
