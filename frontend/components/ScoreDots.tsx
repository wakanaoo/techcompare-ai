interface ScoreDotsProps {
  score: number;
  max?: number;
}

/**
 * スコアを5段階のドットで視覚化する。星評価のようなレビューサイト風の
 * 表現ではなく、技術比較ツールらしい中立的な指標として見せるため、
 * 色は「良い/悪い」を連想させる緑・赤等は使わず、濃淡だけで表現する。
 */
export function ScoreDots({ score, max = 5 }: ScoreDotsProps) {
  const dots = Array.from({ length: max }, (_, i) => i < score);

  return (
    <span className="score-dots" aria-label={`スコア ${score}/${max}`}>
      <span className="score-dots__dots" aria-hidden="true">
        {dots.map((filled, i) => (
          <span
            key={i}
            className={filled ? "score-dots__dot score-dots__dot--filled" : "score-dots__dot"}
          />
        ))}
      </span>
      <span className="score-dots__label">
        {score}/{max}
      </span>
    </span>
  );
}
