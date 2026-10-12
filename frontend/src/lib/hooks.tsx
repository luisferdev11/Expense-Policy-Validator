import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { ApiError } from "../api/client";
import type { ReceiptDetail, ReceiptSummary } from "../api/types";

// Small helpers for local, per-viewer conveniences: every access is guarded (private windows).
export function readStore(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
export function writeStore(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

/** Run `fn` now and every `intervalMs`; keeps the last data while refreshing. */
export function usePolling<T>(fn: () => Promise<T>, deps: unknown[], intervalMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const alive = useRef(true);

  const reload = useCallback(async () => {
    try {
      const result = await fnRef.current();
      if (!alive.current) return;
      setData(result);
      setError(null);
    } catch (e) {
      if (alive.current) setError(e as Error);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    setLoading(true);
    void reload();
    let timer: ReturnType<typeof setInterval> | undefined;
    if (intervalMs > 0) {
      timer = setInterval(() => {
        if (!document.hidden) void reload();
      }, intervalMs);
    }
    return () => {
      alive.current = false;
      if (timer) clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, intervalMs, reload]);

  return { data, error, loading, reload };
}

/**
 * The list endpoint returns summaries only (no merchant, employee or total). Rows need those, so
 * details are fetched once per `receipt_id` + `updated_at` and kept (FINDINGS.md F-01).
 */
export function useDetails(summaries: ReceiptSummary[] | null): Map<string, ReceiptDetail> {
  const cache = useRef(new Map<string, ReceiptDetail>());
  const inflight = useRef(new Set<string>());
  const [, bump] = useState(0);

  useEffect(() => {
    if (!summaries) return;
    const todo = summaries.filter((s) => {
      const key = `${s.receipt_id}:${s.updated_at}`;
      return !cache.current.has(key) && !inflight.current.has(key);
    });
    if (todo.length === 0) return;
    let cancelled = false;
    const queue = [...todo];
    const worker = async () => {
      for (let s = queue.shift(); s; s = queue.shift()) {
        const key = `${s.receipt_id}:${s.updated_at}`;
        inflight.current.add(key);
        try {
          const detail = await api.getReceipt(s.receipt_id);
          cache.current.set(key, detail);
        } catch {
          /* the row stays with the summary's columns */
        } finally {
          inflight.current.delete(key);
        }
        if (!cancelled) bump((n) => n + 1);
      }
    };
    void Promise.all([worker(), worker(), worker(), worker()]);
    return () => {
      cancelled = true;
    };
  }, [summaries]);

  return useMemo(() => {
    const byId = new Map<string, ReceiptDetail>();
    for (const s of summaries ?? []) {
      const d = cache.current.get(`${s.receipt_id}:${s.updated_at}`);
      if (d) byId.set(s.receipt_id, d);
    }
    return byId;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summaries, cache.current.size]);
}

// Actor ---------------------------------------------------------------------------------------
// There is no authentication in this iteration: the actor is free text recorded in each event.

interface ActorCtx {
  actor: string;
  setActor: (name: string) => void;
}
const ActorContext = createContext<ActorCtx>({ actor: "", setActor: () => {} });
export const useActor = () => useContext(ActorContext);

export function ActorProvider({ children }: { children: ReactNode }) {
  const [actor, setActorState] = useState(() => readStore("epv.actor") ?? "");
  const setActor = useCallback((name: string) => {
    setActorState(name);
    writeStore("epv.actor", name);
  }, []);
  return <ActorContext.Provider value={{ actor, setActor }}>{children}</ActorContext.Provider>;
}

// Toasts --------------------------------------------------------------------------------------

interface Toast {
  id: number;
  text: string;
  tone: "ok" | "error";
}
interface ToastCtx {
  toast: (text: string, tone?: Toast["tone"]) => void;
}
const ToastContext = createContext<ToastCtx>({ toast: () => {} });
export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const toast = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = next.current++;
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);
  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.tone}`}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// Theme ---------------------------------------------------------------------------------------

export type Theme = "system" | "light" | "dark";
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => (readStore("epv.theme") as Theme) ?? "system");
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    writeStore("epv.theme", theme);
  }, [theme]);
  const cycle = useCallback(
    () => setTheme((t) => (t === "system" ? "light" : t === "light" ? "dark" : "system")),
    [],
  );
  return [theme, cycle];
}

/** Keyboard shortcuts; ignored while typing in a field or while a dialog is open. */
export function useShortcuts(map: Record<string, () => void>, enabled = true) {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable)) return;
      if (document.querySelector("dialog[open], [role=dialog]")) return;
      const fn = ref.current[e.key.toLowerCase()] ?? ref.current[e.key];
      if (fn) {
        e.preventDefault();
        fn();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
