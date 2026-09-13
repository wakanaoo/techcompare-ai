interface AlertProps {
  tone: "danger";
  /** 人間向けのフレンドリーな主メッセージ。 */
  title: string;
  /** 補足の説明文(任意)。 */
  description?: string;
  /** backendの生のerror_message等、技術的な詳細。<details>で折りたたんで表示する。 */
  details?: string | null;
}

/**
 * フレンドリーな主メッセージと、技術的な詳細(status codeを含む生のエラー文言)を
 * 分離して表示するアラート。詳細はネイティブの<details>で折りたたむため、
 * 追加のstate管理は不要。
 */
export function Alert({ tone, title, description, details }: AlertProps) {
  return (
    <div className={`alert alert--${tone}`} role="alert">
      <p className="alert__title">{title}</p>
      {description && <p className="alert__description">{description}</p>}
      {details && (
        <details className="alert__details">
          <summary>技術的な詳細</summary>
          <pre>{details}</pre>
        </details>
      )}
    </div>
  );
}
