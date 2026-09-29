"use client";

import { useRef, useState, type KeyboardEvent } from "react";

interface UseCaseInputProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  /**
   * curatedなUse Case Examples(呼び出し側で`useMemo`等により、対象ペアが
   * 変わらない限り同じ配列参照を保つこと。参照が変わるたびに現在位置は
   * 先頭へリセットされる)。
   */
  examples: string[];
}

/**
 * "What are you building?"欄(Phase 5C Finishing)。
 *
 * 通常の`<input>`としての入力を一切妨げない: 文字入力・カーソル移動などは
 * すべてブラウザ標準のまま。ここで追加するのは2つだけ:
 *  - 入力欄下の小さく控えめな"↗ Example"ボタン(押すたびにcurated examplesを
 *    1件ずつ順送りする。常時説明を表示する代わりに、`title`属性
 *    (ネイティブtooltip)へ集約している)。
 *  - 入力欄にfocus中、値が「空」または「直前に採用したexampleと完全一致」の
 *    ときだけ、↑/↓キーでexampleを順送り・逆送りする。ユーザーが自分で
 *    文章を書き始めたら(値がどのexampleとも一致しなくなったら)、↑/↓は
 *    一切介入しない(=通常のテキスト入力を邪魔しない)。
 */
export function UseCaseInput({
  id,
  value,
  onChange,
  placeholder,
  disabled,
  examples,
}: UseCaseInputProps) {
  const [exampleIndex, setExampleIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // examplesの中身(参照)が変わった = 比較対象のTechnology pairが変わった、
  // ということなので、循環位置を先頭へ戻す。effect内でのsetStateによる
  // cascading renderを避けるため、render中に調整する
  // (`app/research/[id]/page.tsx`のtrackedIdと同じ既存パターン)。
  const [trackedExamples, setTrackedExamples] = useState(examples);
  if (trackedExamples !== examples) {
    setTrackedExamples(examples);
    setExampleIndex(0);
  }

  const currentExample = examples[exampleIndex];

  /**
   * examplesをdelta分進める/戻す(ボタンクリック・↑↓キー共通)。
   * 値が空、またはまだ「例をそのまま採用しただけ」の状態でなければ、
   * ユーザー自身の入力を上書きしないよう何もしない。実際に値を変更したら
   * trueを返す(呼び出し側でpreventDefaultの要否を判断するため)。
   */
  function advanceExample(delta: number): boolean {
    if (examples.length === 0) return false;

    const inSyncWithExamples = value === "" || value === currentExample;
    if (!inSyncWithExamples) return false;

    if (value === "") {
      // 最初の1回は、今hintに表示されているexampleをそのまま採用する(indexは進めない)。
      onChange(currentExample);
      return true;
    }

    const nextIndex = (exampleIndex + delta + examples.length) % examples.length;
    setExampleIndex(nextIndex);
    onChange(examples[nextIndex]);
    return true;
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;

    const changed = advanceExample(event.key === "ArrowDown" ? 1 : -1);
    if (changed) event.preventDefault();
  }

  return (
    <div className="use-case-input">
      <input
        ref={inputRef}
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
      />
      {examples.length > 0 && (
        <button
          type="button"
          className="use-case-input__example"
          onClick={() => {
            advanceExample(1);
            inputRef.current?.focus();
          }}
          disabled={disabled}
          title="クリックするたびに例を切り替え / 入力欄にフォーカス中は↑↓キーでも切り替え"
        >
          ↗ Example
        </button>
      )}
    </div>
  );
}
