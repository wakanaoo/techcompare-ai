import Link from "next/link";

import type { EvidenceSummary } from "@/lib/api";

interface EvidenceLinksProps {
  evidence: EvidenceSummary[];
}

/**
 * 1件なら"View Evidence"という明確な単一リンク、複数件なら
 * "Evidence · N sources"というラベル + 番号付きの個別リンクを表示する。
 * 同じ「根拠を見る」を縦に何度も並べるのではなく、件数が一目で分かり、
 * かつ全件へ個別にアクセスできる形にする。0件ならmutedな案内を表示する。
 */
export function EvidenceLinks({ evidence }: EvidenceLinksProps) {
  if (evidence.length === 0) {
    return <p className="evidence-links evidence-links--empty">No evidence</p>;
  }

  if (evidence.length === 1) {
    return (
      <Link href={`/evidence/${evidence[0].id}`} className="evidence-links__single">
        View Evidence
      </Link>
    );
  }

  return (
    <div className="evidence-links">
      <span className="evidence-links__count">Evidence · {evidence.length} sources</span>
      <span className="evidence-links__chips">
        {evidence.map((e, index) => (
          <Link
            key={e.id}
            href={`/evidence/${e.id}`}
            className="evidence-links__chip"
            aria-label={`Evidence ${index + 1}`}
          >
            {index + 1}
          </Link>
        ))}
      </span>
    </div>
  );
}
