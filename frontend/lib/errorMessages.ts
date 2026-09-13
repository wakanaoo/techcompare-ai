/**
 * backendが保存するResearch.error_message(例:
 * "LLM API呼び出しでエラーが発生しました(status: 429)。")を、
 * 人間向けのフレンドリーな見出しへ変換する。
 *
 * backendの文言そのもの(status codeを含む)は"technical detail"として
 * 別途保持し、UI側で「技術的な詳細」として補足表示する(Alert参照)。
 *
 * backendの文言の完全一致には依存せず、"status: NNN"というごく単純な
 * パターンと、いくつかのキーワードの部分一致だけで判定する。将来
 * backend側の文言が多少変わっても、フォールバックのフレンドリー文言が
 * 表示されるだけで壊れない設計にしている。
 */

export interface FriendlyError {
  headline: string;
  detail: string | null;
}

const STATUS_CODE_PATTERN = /status:\s*(\d+)/;

export function getFriendlyErrorMessage(rawMessage: string | null): FriendlyError {
  if (!rawMessage) {
    return {
      headline: "原因不明のエラーにより、調査を完了できませんでした。",
      detail: null,
    };
  }

  const match = rawMessage.match(STATUS_CODE_PATTERN);
  const statusCode = match ? Number(match[1]) : null;

  if (statusCode === 429) {
    return {
      headline:
        "AIサービスへのアクセスが集中しており、一時的に制限されました。しばらく待ってからもう一度お試しください。",
      detail: rawMessage,
    };
  }

  if (statusCode === 503) {
    return {
      headline: "AIサービスが一時的に利用できませんでした。しばらく待ってからもう一度お試しください。",
      detail: rawMessage,
    };
  }

  if (statusCode !== null && statusCode >= 500) {
    return {
      headline: "AIサービス側で一時的な問題が発生しました。しばらく待ってからもう一度お試しください。",
      detail: rawMessage,
    };
  }

  if (statusCode === 401 || statusCode === 403) {
    return {
      headline: "AIサービスへの認証に問題が発生しました。",
      detail: rawMessage,
    };
  }

  if (rawMessage.includes("APIキーが設定されていないか無効です")) {
    return {
      headline: "サービスの設定に問題が発生しました。",
      detail: rawMessage,
    };
  }

  if (rawMessage.includes("検索")) {
    return {
      headline: "情報源の検索中に問題が発生しました。しばらく待ってからもう一度お試しください。",
      detail: rawMessage,
    };
  }

  return {
    headline: "調査を完了できませんでした。しばらく待ってからもう一度お試しください。",
    detail: rawMessage,
  };
}
