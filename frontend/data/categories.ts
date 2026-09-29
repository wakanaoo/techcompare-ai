/**
 * Technology Mapのトップレベル7カテゴリ(Phase 5C)。
 *
 * `available: false` のカテゴリはPhase 5C Prototypeではtechnologyデータを
 * 持たない(README/Implementation Plan参照: 全カテゴリを埋める必要はなく、
 * まずserver/data/aiの3カテゴリでvertical sliceを完成させる)。Technology
 * Map側は `available: false` を「Coming soon」表示・クリック不可の扱いにする。
 */

export type CategoryId =
  | "write"
  | "interface"
  | "server"
  | "data"
  | "ai"
  | "run"
  | "develop";

export interface Category {
  id: CategoryId;
  /** カード見出し用の短い名前("Server"等)。 */
  name: string;
  /** nameの下に添える、実際の技術領域名("Backend"等)。 */
  domainLabel: string;
  /** 初学者向けの一言("裏側の処理をどう作る?")。 */
  question: string;
  /** Phase 5C Prototypeでtechnologyデータを持つかどうか。 */
  available: boolean;
}

export const CATEGORIES: Category[] = [
  {
    id: "write",
    name: "Write",
    domainLabel: "Programming Languages",
    question: "何でプログラムを書く?",
    available: false,
  },
  {
    id: "interface",
    name: "Interface",
    domainLabel: "Frontend",
    question: "ユーザーが触る画面をどう作る?",
    available: false,
  },
  {
    id: "server",
    name: "Server",
    domainLabel: "Backend",
    question: "裏側の処理をどう作る?",
    available: true,
  },
  {
    id: "data",
    name: "Data",
    domainLabel: "Data & Database",
    question: "データをどう保存・検索する?",
    available: true,
  },
  {
    id: "ai",
    name: "AI",
    domainLabel: "AI / LLM",
    question: "AIをどう組み込む?",
    available: true,
  },
  {
    id: "run",
    name: "Run",
    domainLabel: "Infrastructure & Deployment",
    question: "どう動かして公開する?",
    available: false,
  },
  {
    id: "develop",
    name: "Develop",
    domainLabel: "Development Tools",
    question: "どう開発・管理する?",
    available: false,
  },
];
