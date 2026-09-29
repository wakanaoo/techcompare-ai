import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { UseCaseInput } from "./UseCaseInput";

const EXAMPLES = ["例文A", "例文B", "例文C"];

/** UseCaseInputは制御コンポーネントなので、実際の親コンポーネントと同じように
 *  valueをstateで持つ薄いwrapperを介してレンダリングする。 */
function ControlledUseCaseInput({ examples = EXAMPLES }: { examples?: string[] }) {
  const [value, setValue] = useState("");
  return (
    <UseCaseInput value={value} onChange={setValue} examples={examples} placeholder="例: ..." />
  );
}

describe("UseCaseInput", () => {
  it("shows a subtle 'Example' action without filling the input", () => {
    render(<ControlledUseCaseInput />);
    expect(screen.getByRole("textbox")).toHaveValue("");
    expect(screen.getByRole("button", { name: "↗ Example" })).toBeInTheDocument();
  });

  it("fills the input and moves focus into it when the Example action is clicked", () => {
    render(<ControlledUseCaseInput />);
    fireEvent.click(screen.getByRole("button", { name: "↗ Example" }));

    const input = screen.getByRole("textbox");
    expect(input).toHaveValue("例文A");
    expect(input).toHaveFocus();
  });

  it("cycles to the next example on each click, instead of repeating the same one", () => {
    render(<ControlledUseCaseInput />);
    const button = screen.getByRole("button", { name: "↗ Example" });
    const input = screen.getByRole("textbox");

    fireEvent.click(button); // adopt 例文A (先頭、indexは進めない)
    expect(input).toHaveValue("例文A");

    fireEvent.click(button); // -> 例文B
    expect(input).toHaveValue("例文B");

    fireEvent.click(button); // -> 例文C
    expect(input).toHaveValue("例文C");

    fireEvent.click(button); // 一周して例文Aに戻る
    expect(input).toHaveValue("例文A");
  });

  it("does not overwrite the value by clicking Example once the user has typed their own text", () => {
    render(<ControlledUseCaseInput />);
    const input = screen.getByRole("textbox");

    fireEvent.change(input, { target: { value: "自分で書いた文章" } });
    fireEvent.click(screen.getByRole("button", { name: "↗ Example" }));

    expect(input).toHaveValue("自分で書いた文章");
  });

  it("ArrowDown on an empty field adopts the currently hinted example without advancing", () => {
    render(<ControlledUseCaseInput />);
    const input = screen.getByRole("textbox");

    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input).toHaveValue("例文A");
  });

  it("cycles forward and backward through examples while the value stays in sync", () => {
    render(<ControlledUseCaseInput />);
    const input = screen.getByRole("textbox");

    fireEvent.keyDown(input, { key: "ArrowDown" }); // adopt 例文A
    fireEvent.keyDown(input, { key: "ArrowDown" }); // -> 例文B
    expect(input).toHaveValue("例文B");

    fireEvent.keyDown(input, { key: "ArrowDown" }); // -> 例文C
    expect(input).toHaveValue("例文C");

    fireEvent.keyDown(input, { key: "ArrowDown" }); // wraps back to 例文A
    expect(input).toHaveValue("例文A");

    fireEvent.keyDown(input, { key: "ArrowUp" }); // wraps backward to 例文C
    expect(input).toHaveValue("例文C");
  });

  it("does not touch the value with ArrowDown/ArrowUp once the user has typed their own text", () => {
    render(<ControlledUseCaseInput />);
    const input = screen.getByRole("textbox");

    fireEvent.change(input, { target: { value: "自分で書いた文章" } });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowUp" });

    expect(input).toHaveValue("自分で書いた文章");
  });

  it("renders no hint UI when there are no examples", () => {
    render(<ControlledUseCaseInput examples={[]} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
