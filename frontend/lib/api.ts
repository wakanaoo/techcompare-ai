/**
 * Backend(FastAPI)を呼び出すための最小限のAPIクライアント。
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type ResearchStatus = "pending" | "researching" | "completed" | "failed";
export type Winner = "item_a" | "item_b" | "tie";
export type Side = "item_a" | "item_b";

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

export interface EvidenceSummary {
  id: number;
  source_id: number;
  source_title: string;
  source_url: string;
  // このEvidenceがitem_a/item_bどちらの主張を裏付けるものか。
  side: Side;
  claim: string;
  evidence_text: string;
}

export interface ComparisonRow {
  id: number;
  criterion: string;
  criterion_label: string;
  item_a_summary: string;
  item_b_summary: string;
  item_a_score: number;
  item_b_score: number;
  winner: Winner;
  evidence: EvidenceSummary[];
}

export interface SourceSummary {
  id: number;
  title: string;
  url: string;
}

export interface ResearchResult {
  research_id: number;
  item_a: string;
  item_b: string;
  goal: string;
  recommendation: Recommendation;
  comparisons: ComparisonRow[];
  sources: SourceSummary[];
}

export interface EvidenceDetail {
  id: number;
  side: Side;
  // sideに対応する実際の技術名(例: "FastAPI")。
  side_label: string;
  claim: string;
  evidence_text: string;
  source_title: string;
  source_url: string;
  comparison_id: number;
  research_id: number;
  criterion_label: string;
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

export async function getEvidence(id: string): Promise<EvidenceDetail> {
  const response = await fetch(`${API_BASE_URL}/evidence/${id}`);

  if (response.status === 404) {
    throw new Error("指定されたEvidenceが見つかりません");
  }
  if (!response.ok) {
    throw new Error(`Evidenceの取得に失敗しました (status: ${response.status})`);
  }

  return response.json();
}

export interface CriterionSuggestion {
  name: string;
  reason: string;
}

export interface SuggestCriteriaInput {
  item_a: string;
  item_b: string;
  goal: string;
  existing_criteria: string[];
}

export interface SuggestCriteriaResult {
  suggestions: CriterionSuggestion[];
}

/**
 * Suggest Points(POST /suggest-criteria)。Geminiのみを1回呼ぶ補助API
 * (Tavilyは呼ばない、Research/Source/Evidenceは作らない)。必ず明示的な
 * button actionから呼び出すこと(入力のたびに自動呼び出ししない)。
 */
export async function suggestCriteria(
  input: SuggestCriteriaInput,
): Promise<SuggestCriteriaResult> {
  const response = await fetch(`${API_BASE_URL}/suggest-criteria`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail ?? `status: ${response.status}`;
    throw new Error(`比較ポイント候補の取得に失敗しました (${detail})`);
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
