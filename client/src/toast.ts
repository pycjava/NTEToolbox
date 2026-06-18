export type ToastKind = "success" | "error" | "info";

export type Toast = {
  id: number;
  kind: ToastKind;
  message: string;
};

/** 同屏最多可见条数，溢出丢弃最旧的，避免堆叠压满屏幕 */
export const TOAST_MAX_VISIBLE = 3;

/** 自动消失时长（毫秒）—— error 留更久，给用户充分阅读时间 */
export const TOAST_TTL_MS: Record<ToastKind, number> = {
  success: 4000,
  info: 4000,
  error: 5000
};

let nextId = 1;

/**
 * 创建一个 toast。
 * id 单调递增；pruneToasts/dismissToast 依赖该性质决定"最旧"。
 */
export function createToast(kind: ToastKind, message: string): Toast {
  return { id: nextId++, kind, message };
}

/** 追加一条 toast（不裁剪，调用方按需 prune） */
export function addToast(toasts: Toast[], toast: Toast): Toast[] {
  return [...toasts, toast];
}

/** 裁剪到可见上限，保留 id 最大的若干条（即最新的） */
export function pruneToasts(toasts: Toast[]): Toast[] {
  if (toasts.length <= TOAST_MAX_VISIBLE) return toasts;
  return [...toasts]
    .sort((a, b) => a.id - b.id)
    .slice(toasts.length - TOAST_MAX_VISIBLE);
}

/** 按 id 移除一条；id 不存在时原样返回 */
export function dismissToast(toasts: Toast[], id: number): Toast[] {
  return toasts.filter((toast) => toast.id !== id);
}
