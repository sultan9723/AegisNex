import { toast } from "sonner";

type UndoAction = () => Promise<boolean>;

const undoHandlers = new Map<string, UndoAction>();
const UNDO_TIMEOUT = 10000;

export function withUndo(
  id: string,
  execute: () => Promise<unknown>,
  undo: UndoAction,
  messages: { success: string; error: string; undo: string },
) {
  return async () => {
    try {
      await execute();
      const dismiss = toast.success(messages.success, {
        action: {
          label: "Undo",
          onClick: () => {
            undo().then((ok) => {
              if (ok) toast.success(messages.undo);
              else toast.error("Undo failed");
            });
          },
        },
        duration: UNDO_TIMEOUT,
      });
    } catch {
      toast.error(messages.error);
    }
  };
}
