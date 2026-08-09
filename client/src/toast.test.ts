import { beforeEach, describe, expect, it } from "vitest";

import {
  addToast,
  createToast,
  dismissToast,
  pruneToasts,
  TOAST_MAX_VISIBLE
} from "./toast";

describe("toast", () => {
  beforeEach(() => {
    // 重置 id 计数器，保证用例之间稳定
    createToast("info", "reset");
  });

  it("assigns strictly increasing ids", () => {
    const first = createToast("success", "a");
    const second = createToast("error", "b");
    const third = createToast("info", "c");

    expect(second.id).toBeGreaterThan(first.id);
    expect(third.id).toBeGreaterThan(second.id);
  });

  it("carries kind and message unchanged", () => {
    const toast = createToast("error", "启动失败");

    expect(toast.kind).toBe("error");
    expect(toast.message).toBe("启动失败");
  });

  it("appends a toast to an empty list", () => {
    const toast = createToast("info", "hi");

    expect(addToast([], toast)).toEqual([toast]);
  });

  it("appends to the end of existing toasts", () => {
    const a = createToast("info", "a");
    const b = createToast("info", "b");
    const c = createToast("info", "c");

    expect(addToast([a, b], c)).toEqual([a, b, c]);
  });

  it("prunes the oldest toasts beyond the visible limit", () => {
    const toasts = [
      createToast("info", "0"),
      createToast("info", "1"),
      createToast("info", "2"),
      createToast("info", "3")
    ];

    const pruned = pruneToasts(toasts);

    expect(pruned).toHaveLength(TOAST_MAX_VISIBLE);
    // 丢弃最旧（id 最小），保留最新的
    expect(pruned.map((t) => t.message)).toEqual(["1", "2", "3"]);
  });

  it("keeps all toasts when under the limit", () => {
    const toasts = [createToast("info", "a"), createToast("info", "b")];

    expect(pruneToasts(toasts)).toHaveLength(2);
  });

  it("removes a toast by id", () => {
    const a = createToast("info", "a");
    const b = createToast("info", "b");

    expect(dismissToast([a, b], a.id)).toEqual([b]);
  });

  it("leaves the list unchanged when the id is absent", () => {
    const a = createToast("info", "a");

    expect(dismissToast([a], 9999)).toEqual([a]);
  });
});
