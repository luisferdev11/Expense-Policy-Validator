import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { ReceiptList, ReceiptSummary } from "../api/types";
import { usePolling } from "./hooks";

interface ReceiptsCtx {
  summaries: ReceiptSummary[];
  total: number;
  loading: boolean;
  error: Error | null;
  reload: () => Promise<void>;
}

const Ctx = createContext<ReceiptsCtx>({
  summaries: [],
  total: 0,
  loading: true,
  error: null,
  reload: async () => {},
});
export const useReceipts = () => useContext(Ctx);

/** One shared, polled copy of the receipt list: the nav counts, the queue and insights read it. */
export function ReceiptsProvider({ children }: { children: ReactNode }) {
  const { data, loading, error, reload } = usePolling<ReceiptList>(
    () => api.listReceipts({ limit: 500 }),
    [],
    4000,
  );
  return (
    <Ctx.Provider
      value={{ summaries: data?.items ?? [], total: data?.total ?? 0, loading, error, reload }}
    >
      {children}
    </Ctx.Provider>
  );
}
