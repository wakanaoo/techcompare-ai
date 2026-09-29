"use client";

import { InfoTooltip } from "./InfoTooltip";

interface CriterionChipProps {
  label: string;
  selected: boolean;
  disabled?: boolean;
  onToggle: () => void;
  /** 説明があるBase Pointだけ、隣にInfoTooltipの"ⓘ"トリガーを併設する。 */
  description?: string;
}

/**
 * Base Point 1件分のchip(選択トグル)。
 *
 * chip本体(選択トグル)とInfoTooltip("ⓘ")は、HTMLのbutton内buttonを避けるため
 * 兄弟要素として並べる(`.chip-with-info`で見た目上1つのpillにまとめる。
 * `app/globals.css`参照)。
 */
export function CriterionChip({
  label,
  selected,
  disabled,
  onToggle,
  description,
}: CriterionChipProps) {
  const chipButton = (
    <button
      type="button"
      className="chip"
      aria-pressed={selected}
      onClick={onToggle}
      disabled={disabled}
    >
      {label}
    </button>
  );

  if (!description) return chipButton;

  return (
    <span className="chip-with-info">
      {chipButton}
      <InfoTooltip triggerLabel={`${label}の説明`} description={description} />
    </span>
  );
}
