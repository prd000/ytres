"use client";

import { useActionState, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  deleteProject,
  type DeleteProjectState,
} from "@/app/(app)/project/actions";

interface DeleteProjectButtonProps {
  projectId: string;
}

export function DeleteProjectButton({ projectId }: DeleteProjectButtonProps) {
  const [open, setOpen] = useState(false);
  const boundDelete = deleteProject.bind(null, projectId);

  const [state, formAction, isDeleting] = useActionState<
    DeleteProjectState,
    FormData
  >(boundDelete, undefined);

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button className="shrink-0 inline-flex items-center justify-center h-8 px-3 text-button text-muted border border-hairline rounded-md hover:border-error hover:text-error transition-colors text-sm">
          Delete
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-[#141413]/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-panel -translate-x-1/2 -translate-y-1/2 rounded-lg bg-surface-card border border-hairline p-6 shadow-lg">
          <Dialog.Title className="text-title-sm text-ink mb-2">
            Delete project?
          </Dialog.Title>
          <Dialog.Description className="text-body-sm text-muted mb-6">
            This permanently removes the project and all of its subtopics,
            sources, chat, and reports. This can&rsquo;t be undone.
          </Dialog.Description>

          {state?.error && (
            <p className="text-body-sm text-error mb-4">{state.error}</p>
          )}

          <div className="flex items-center justify-end gap-3">
            <Dialog.Close asChild>
              <button
                type="button"
                disabled={isDeleting}
                className="h-9 px-4 text-button text-ink border border-hairline rounded-md hover:bg-surface-soft transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
            </Dialog.Close>
            <form action={formAction}>
              <button
                type="submit"
                disabled={isDeleting}
                className="h-9 px-4 text-button bg-error text-on-primary rounded-md hover:bg-error/90 active:bg-error/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isDeleting ? "Deleting…" : "Delete project"}
              </button>
            </form>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
