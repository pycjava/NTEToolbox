import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const { invokeMock } = vi.hoisted(() => ({
  invokeMock: vi.fn()
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock
}));

afterEach(() => {
  invokeMock.mockReset();
  cleanup();
});

describe("App", () => {
  it("renders the client shell without a React global", () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    expect(screen.getByRole("heading", { name: "MaaToolbox" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "NTEToolbox" })).toBeTruthy();
    expect(screen.getByText("异环工具箱")).toBeTruthy();
    expect(screen.queryByRole("option", { name: "模拟器窗口 1" })).toBeNull();
  });

  it("opens piano configuration with keyboard input fields", () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "编辑弹钢琴 (键盘输入)" }));

    const dialog = screen.getByRole("dialog", { name: "弹钢琴 (键盘输入)" });
    expect(within(dialog).getByText("MIDI 文件路径")).toBeTruthy();
    expect(within(dialog).getByText("默认 BPM")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("36")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("速率不变")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("1")).toBeTruthy();
  });

  it("opens realtime assist configuration with pickup and screenshot controls", () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "编辑实时辅助" }));

    const dialog = screen.getByRole("dialog", { name: "实时辅助" });
    expect(within(dialog).getByText("自动拾取")).toBeTruthy();
    expect(within(dialog).getByText("自动拾取 - 永远拾取")).toBeTruthy();
    expect(within(dialog).getByText("S级鱼截图")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("screenshots/s_fish")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("5")).toBeTruthy();
  });

  it("keeps running state inline on the feature row after launch", () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    expect(screen.queryByRole("button", { name: "实时视图" })).toBeNull();

    const fishRow = screen.getByRole("article", { name: /钓鱼/ });
    const pianoRow = screen.getByRole("article", { name: /弹钢琴/ });

    fireEvent.click(within(fishRow).getByRole("button", { name: "启动" }));

    expect(within(fishRow).getByText("运行中")).toBeTruthy();
    expect(within(fishRow).getByRole("button", { name: "暂停" })).toBeTruthy();
    expect(within(fishRow).getByRole("button", { name: "停止" })).toBeTruthy();
    expect(within(pianoRow).getByText("就绪")).toBeTruthy();
  });

  it("shows global settings in the client settings dialog and saves local values", () => {
    invokeMock.mockResolvedValue(null);
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

  it("persists feature configuration through the Tauri backend", async () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "编辑钓鱼" }));
    const dialog = screen.getByRole("dialog", { name: "钓鱼" });
    const baitCountInput = within(dialog).getByLabelText("买饵次数");

    fireEvent.change(baitCountInput, { target: { value: "9" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));

    expect(invokeMock).toHaveBeenCalledWith("save_client_config", expect.objectContaining({
      config: expect.objectContaining({
        games: expect.objectContaining({
          nte: expect.objectContaining({
            features: expect.objectContaining({
              fish: expect.objectContaining({
                optionValues: expect.objectContaining({ "买饵次数": "9" }),
                pipelineOverride: expect.objectContaining({
                  "钓鱼": expect.objectContaining({
                    attach: expect.objectContaining({ "买饵次数": 9 })
                  })
                })
              })
            })
          })
        })
      })
    }));
  });

  it("starts and stops a feature through the Maa execution bridge", async () => {
    invokeMock.mockImplementation((command: string) => {
      if (command === "load_client_config") return Promise.resolve(null);
      if (command === "start_maa_task") return Promise.resolve({ runState: "running" });
      if (command === "stop_maa_task") return Promise.resolve({ runState: "idle" });
      return Promise.resolve(null);
    });

    render(<App />);

    const fishRow = screen.getByRole("article", { name: /钓鱼/ });
    fireEvent.click(within(fishRow).getByRole("button", { name: "启动" }));

    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith("start_maa_task", {
        request: expect.objectContaining({
          gameId: "nte",
          featureId: "fish",
          taskName: "钓鱼",
          controllerName: "Win PostMessage (默认)",
          resourceName: "默认",
          optionKeys: [
            "钓鱼终止时间开关",
            "溜鱼设置",
            "卖鱼买换饵开关",
            "卖鱼买换饵设置"
          ],
          optionValues: expect.objectContaining({
            "钓鱼终止时间开关": false,
            "买饵次数": "4"
          }),
          globalOptionKey: "全局设置",
          globalSettingsValues: expect.objectContaining({
            debug_mode_switch: "0",
            logging_switch: "1"
          })
        })
      });
    });
    expect(within(fishRow).getByText("运行中")).toBeTruthy();

    fireEvent.click(within(fishRow).getByRole("button", { name: "停止" }));

    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith("stop_maa_task", {
        gameId: "nte",
        featureId: "fish"
      });
    });
    expect(within(fishRow).getByText("就绪")).toBeTruthy();
  });
});
