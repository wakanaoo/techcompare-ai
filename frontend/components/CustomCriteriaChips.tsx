"use client";

interface CustomCriteriaChipsProps {
  /** 固定候補・AI提案のどちらでもない、自由入力で追加されたcriteria。 */
  chips: string[];
  onRemove: (value: string) => void;
  disabled?: boolean;
}

/**
 * 自由入力で追加したcriteriaを、削除可能なchipとして一覧表示する
 * (Phase 5C Finishingから、Direct Compare/Compare Setup両方で共通利用)。
 */
export function CustomCriteriaChips({ chips, onRemove, disabled }: CustomCriteriaChipsProps) {
  if (chips.length === 0) return null;

  return (
    <>
      <p
        style={{
          fontSize: "0.78rem",
          color: "var(--color-text-subtle)",
          marginTop: "var(--space-3)",
          marginBottom: "var(--space-1)",
        }}
      >
        追加した項目
      </p>
      <div className="chip-group" role="group" aria-label="追加した項目">
        {chips.map((text) => (
          <button
            key={text}
            type="button"
            className="chip"
            aria-pressed="true"
            onClick={() => onRemove(text)}
            disabled={disabled}
            title="クリックして削除"
          >
            {text} ✕
          </button>
        ))}
      </div>
    </>
  );
}
