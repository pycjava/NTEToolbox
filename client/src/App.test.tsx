import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
});

describe("App", () => {
  it("renders the client shell without a React global", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "NTEToolbox" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "异环 NTE" })).toBeTruthy();
  });

  it("opens piano configuration with keyboard input fields", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "编辑弹钢琴" }));

    const dialog = screen.getByRole("dialog", { name: "弹钢琴" });
    expect(within(dialog).getByText("MIDI 文件路径")).toBeTruthy();
    expect(within(dialog).getByText("默认 BPM")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("36")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("速率不变")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("1")).toBeTruthy();
  });

  it("opens realtime assist configuration with pickup and screenshot controls", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "编辑实时辅助" }));

    const dialog = screen.getByRole("dialog", { name: "实时辅助" });
    expect(within(dialog).getByText("自动拾取")).toBeTruthy();
    expect(within(dialog).getByText("自动拾取 - 永远拾取")).toBeTruthy();
    expect(within(dialog).getByText("S级鱼截图")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("screenshots/s_fish")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("5")).toBeTruthy();
  });

  it("shows global settings in the client settings dialog and saves local values", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    const dialog = screen.getByRole("dialog", { name: "设置" });
    expect(within(dialog).getByText("全局设置")).toBeTruthy();

    const debugInput = within(dialog).getByLabelText("debug 模式开关 (`1` 为开 `0` 为关)");
    const loggingInput = within(dialog).getByLabelText("日志开关 (`1` 为开 `0` 为关)");
    expect(debugInput).toHaveProperty("value", "0");
    expect(loggingInput).toHaveProperty("value", "1");

    fireEvent.change(debugInput, { target: { value: "1" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));

    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    const reopenedDialog = screen.getByRole("dialog", { name: "设置" });
    expect(within(reopenedDialog).getByLabelText("debug 模式开关 (`1` 为开 `0` 为关)")).toHaveProperty("value", "1");
    expect(within(reopenedDialog).getByLabelText("日志开关 (`1` 为开 `0` 为关)")).toHaveProperty("value", "1");
  });
});
