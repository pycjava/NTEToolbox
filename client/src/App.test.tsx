import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const { invokeMock, listenMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  listenMock: vi.fn().mockResolvedValue(vi.fn())
}));

vi.mock("@tauri-apps/api/core", () => ({
  invoke: invokeMock
}));

vi.mock("@tauri-apps/api/event", () => ({
  listen: listenMock
}));

afterEach(() => {
  invokeMock.mockReset();
  listenMock.mockResolvedValue(vi.fn());
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

  it("opens piano configuration with track selector and keyboard input fields", () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "编辑弹钢琴 (键盘输入)" }));

    const dialog = screen.getByRole("dialog", { name: "弹钢琴 (键盘输入)" });
    expect(within(dialog).getByText("选择曲目")).toBeTruthy();
    expect(within(dialog).getByText("默认 BPM")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("36")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("速率不变")).toBeTruthy();
    expect(within(dialog).getByDisplayValue("1")).toBeTruthy();
  });

  it("shows a public-domain Mutopia MIDI browser in the library tab", async () => {
    invokeMock.mockImplementation((command: string) => {
      if (command === "list_mutopia_public_domain_midi") {
        return Promise.resolve([
          {
            id: "rumores-de-la-caleta",
            title: "Rumores de la Caleta",
            composer: "I. M. F. Albéniz",
            instrument: "Piano",
            style: "Romantic",
            license: "Public Domain",
            midiUrl: "https://www.mutopiaproject.org/ftp/AlbenizIMF/O71/Rumores_de_la-caleta/Rumores_de_la-caleta.mid",
            sourceUrl: "https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=898"
          }
        ]);
      }
      return Promise.resolve(null);
    });

    render(<App />);

    fireEvent.click(screen.getByRole("tab", { name: /MIDI 曲库/ }));

    expect(screen.getByText("Mutopia 公共领域 MIDI")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "加载曲库" }));

    await waitFor(() => {
      expect(screen.getByText("Rumores de la Caleta")).toBeTruthy();
    });
    expect(screen.getByText("Public Domain")).toBeTruthy();
    expect(screen.queryByText("Creative Commons Attribution-ShareAlike 4.0")).toBeNull();
  });

  it("downloads a Mutopia MIDI in library tab and shows downloaded badge", async () => {
    invokeMock.mockImplementation((command: string) => {
      if (command === "list_mutopia_public_domain_midi") {
        return Promise.resolve([
          {
            id: "andre-sonatine",
            title: "Sonatine",
            composer: "J. André",
            instrument: "Piano",
            style: "Classical",
            license: "Public Domain",
            midiUrl: "https://www.mutopiaproject.org/ftp/AndreJ/O34/andre-sonatine/andre-sonatine.mid",
            sourceUrl: "https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=207"
          }
        ]);
      }
      if (command === "download_mutopia_midi") {
        return Promise.resolve("C:\\midi\\andre-sonatine.mid");
      }
      return Promise.resolve(null);
    });

    render(<App />);

    fireEvent.click(screen.getByRole("tab", { name: /MIDI 曲库/ }));
    fireEvent.click(screen.getByRole("button", { name: "加载曲库" }));
    await waitFor(() => {
      expect(screen.getByText("Sonatine")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "下载 Sonatine" }));

    await waitFor(() => {
      expect(screen.getByText("已下载 ✓")).toBeTruthy();
    });
    expect(invokeMock).toHaveBeenCalledWith("download_mutopia_midi", {
      request: expect.objectContaining({
        title: "Sonatine",
        midiUrl: "https://www.mutopiaproject.org/ftp/AndreJ/O34/andre-sonatine/andre-sonatine.mid",
        license: "Public Domain"
      })
    });
  });

  it("opens fishing configuration with independent fish screenshot controls", () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "编辑钓鱼" }));

    const dialog = screen.getByRole("dialog", { name: "钓鱼" });
    expect(within(dialog).getByText("S级鱼截图")).toBeTruthy();
    expect(within(dialog).getByText("金色鱼截图")).toBeTruthy();
    expect(within(dialog).queryByLabelText("S级鱼截图保存目录")).toBeNull();
    expect(within(dialog).queryByDisplayValue("screenshots/s_fish")).toBeNull();
    expect(within(dialog).getByLabelText("鱼截图冷却时间 (秒)")).toHaveProperty("value", "5");
  });

  it("opens realtime assist configuration with pickup controls only", () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "编辑实时辅助" }));

    const dialog = screen.getByRole("dialog", { name: "实时辅助" });
    expect(within(dialog).getByText("自动拾取")).toBeTruthy();
    expect(within(dialog).getByText("自动拾取 - 永远拾取")).toBeTruthy();
    expect(within(dialog).queryByText("S级鱼截图")).toBeNull();
    expect(within(dialog).queryByDisplayValue("screenshots/s_fish")).toBeNull();
  });

  it("keeps running state inline on the feature row after launch", async () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    const fishRow = screen.getByRole("article", { name: /钓鱼/ });
    const pianoRow = screen.getByRole("article", { name: /弹钢琴/ });

    fireEvent.click(within(fishRow).getByRole("button", { name: "启动" }));

    // 点击后先进入 starting（启动中）过渡态
    expect(within(fishRow).getByText("启动中")).toBeTruthy();

    // start_maa_task 异步 resolve 后进入 running（运行中）
    await waitFor(() => expect(within(fishRow).getByText("运行中")).toBeTruthy());
    expect(within(fishRow).queryByRole("button", { name: "暂停" })).toBeNull();
    expect(within(fishRow).getByRole("button", { name: "结束任务" })).toBeTruthy();
    expect(within(pianoRow).getByText("就绪")).toBeTruthy();
  });

  it("does not show copy configuration actions in the feature list", () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    expect(screen.queryByRole("button", { name: /复制.*配置/ })).toBeNull();
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
            "卖鱼买换饵设置",
            "钓鱼_S级鱼截图",
            "钓鱼_金色鱼截图",
            "钓鱼_鱼截图_设置"
          ],
          optionValues: expect.objectContaining({
            "钓鱼终止时间开关": false,
            "买饵次数": "4",
            "钓鱼_S级鱼截图": true,
            "钓鱼_金色鱼截图": false,
            "鱼截图冷却时间": "5"
          }),
          globalOptionKey: "全局设置",
          globalSettingsValues: expect.objectContaining({
            debug_mode_switch: "0",
            logging_switch: "1"
          })
        })
      });
    });
    const startCall = invokeMock.mock.calls.find(([command]) => command === "start_maa_task");
    expect(startCall?.[1]?.request.optionValues).not.toHaveProperty("S级鱼截图保存目录");
    expect(within(fishRow).getByText("运行中")).toBeTruthy();

    fireEvent.click(within(fishRow).getByRole("button", { name: "结束任务" }));

    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith("stop_maa_task", {
        gameId: "nte",
        featureId: "fish"
      });
    });
    expect(within(fishRow).getByText("就绪")).toBeTruthy();
  });

  it("updates a feature row when MaaPiCli exits in the background", async () => {
    invokeMock.mockImplementation((command: string) => {
      if (command === "poll_maa_task_states") {
        return Promise.resolve([
          {
            gameId: "nte",
            featureId: "fish",
            runState: "completed",
            exitCode: 0
          }
        ]);
      }
      return Promise.resolve(null);
    });

    render(<App />);

    const fishRow = screen.getAllByRole("article")[0];
    await waitFor(() => {
      expect(fishRow.querySelector(".run-completed")).toBeTruthy();
    });
  });

  it("switches between features and live view tabs", () => {
    invokeMock.mockResolvedValue(null);
    render(<App />);

    // Default view is features — feature rows are visible
    expect(screen.getByRole("article", { name: /钓鱼/ })).toBeTruthy();

    // Live view tab exists and can be clicked
    const liveTab = screen.getByRole("tab", { name: /实时视图/ });
    expect(liveTab).toBeTruthy();

    // Switch to live view
    fireEvent.click(liveTab);

    // Feature rows should be gone, placeholder should appear
    expect(screen.queryByRole("article", { name: /钓鱼/ })).toBeNull();
    expect(screen.getByText("请先连接目标窗口")).toBeTruthy();

    // Switch back to features
    fireEvent.click(screen.getByRole("tab", { name: /功能列表/ }));
    expect(screen.getByRole("article", { name: /钓鱼/ })).toBeTruthy();
    expect(screen.queryByText("请先连接目标窗口")).toBeNull();
  });
});
