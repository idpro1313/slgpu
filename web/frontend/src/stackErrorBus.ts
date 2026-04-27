/** Глобальная шина для 409 missing_stack_params (без лишних зависимостей). */

export type StackErrorPayload = { keys: string[]; scope: string; detail?: string };

let _handler: ((p: StackErrorPayload) => void) | null = null;

export function setMissingStackParamsHandler(h: ((p: StackErrorPayload) => void) | null): void {
  _handler = h;
}

export function publishMissingStackParams(p: StackErrorPayload): void {
  _handler?.(p);
}
