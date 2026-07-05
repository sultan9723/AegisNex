"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";

export type ActionState = "idle" | "loading" | "success" | "error";

export function useAction<TData = unknown, TInput = void>() {
  const [state, setState] = useState<ActionState>("idle");
  const [error, setError] = useState<string | null>(null);

  const execute = useCallback(
    async (
      fn: (input: TInput) => Promise<TData>,
      input: TInput,
      messages?: { loading?: string; success?: string; error?: string },
    ): Promise<TData | null> => {
      setState("loading");
      setError(null);
      const loadingToast = messages?.loading ? toast.loading(messages.loading) : undefined;

      try {
        const result = await fn(input);
        setState("success");
        if (loadingToast) toast.dismiss(loadingToast);
        if (messages?.success) toast.success(messages.success);
        return result;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "An unexpected error occurred";
        setState("error");
        setError(msg);
        if (loadingToast) toast.dismiss(loadingToast);
        toast.error(messages?.error ?? msg);
        return null;
      }
    },
    [],
  );

  const reset = useCallback(() => {
    setState("idle");
    setError(null);
  }, []);

  return { state, error, execute, reset, isLoading: state === "loading" };
}
