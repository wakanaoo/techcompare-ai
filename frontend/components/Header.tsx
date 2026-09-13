import Link from "next/link";

/**
 * アプリ共通のヘッダー。ロゴ(アプリ名)からトップ(New Research)へ戻れる。
 * インタラクティブな状態を持たないためServer Componentのままでよい。
 */
export function Header() {
  return (
    <header className="app-header">
      <div className="app-header__inner">
        <Link href="/" className="app-header__brand">
          TechCompare AI
        </Link>
      </div>
    </header>
  );
}
