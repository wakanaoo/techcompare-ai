"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Spinner } from "./Spinner";

type ButtonVariant = "primary" | "secondary";

interface CommonProps {
  variant?: ButtonVariant;
  /** true の間はSpinnerを表示し、二重送信を防ぐためdisabledを強制する。 */
  loading?: boolean;
  children: ReactNode;
}

type ButtonAsButton = CommonProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
    href?: undefined;
  };

type ButtonAsLink = CommonProps & {
  href: string;
  /** hrefが指定された場合は<Link>として描画するため、button固有属性は受け付けない。 */
};

type ButtonProps = ButtonAsButton | ButtonAsLink;

/**
 * primary/secondaryのvariantと、loading状態(Spinner + disabled強制)を持つ
 * 共通ボタン。href付きで呼ぶと見た目はボタンのまま<Link>として振る舞う
 * (「入力画面に戻る」のような画面遷移導線に使う)。
 */
export function Button(props: ButtonProps) {
  const variant = props.variant ?? "primary";
  const className = `btn btn--${variant}`;

  if ("href" in props && props.href !== undefined) {
    const { href, children } = props;
    return (
      <Link href={href} className={className}>
        {children}
      </Link>
    );
  }

  const { loading, children, disabled, variant: _omit, ...rest } = props as ButtonAsButton;
  void _omit;

  return (
    <button className={className} disabled={disabled || loading} {...rest}>
      {loading && <Spinner />}
      {children}
    </button>
  );
}
