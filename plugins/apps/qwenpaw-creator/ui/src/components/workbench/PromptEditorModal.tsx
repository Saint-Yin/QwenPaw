import { useEffect, useRef, useState } from "react";
import { Button, Modal } from "antd";
import { useTranslation } from "react-i18next";
import PromptTokenEditor, {
  type PromptTokenEditorHandle,
} from "@/components/workbench/PromptTokenEditor";
import type { PromptRichToken } from "@/components/workbench/PromptRichBlock";

/** A project asset that may be added as a brand-new [Image N] reference. */
export interface PromptRefCandidate {
  id: string;
  name: string;
  thumbUrl: string | null;
}

/**
 * Shared fullscreen prompt editor (R2V workbench and the asset library use
 * the same editing mode): a token-pill canvas plus a right-hand reference
 * rail whose entries insert the pill itself at the caret. `candidates` lists
 * project assets not yet bound as references — picking one assigns the next
 * [Image N] index, inserts its pill, and reports the binding on 完成 so the
 * host can persist it alongside the prompt. Local draft only.
 */
export default function PromptEditorModal({
  open,
  label,
  initialValue,
  tokens,
  candidates = [],
  disabled = false,
  onCancel,
  onDone,
}: {
  open: boolean;
  label: string;
  initialValue: string;
  tokens: PromptRichToken[];
  candidates?: PromptRefCandidate[];
  disabled?: boolean;
  onCancel: () => void;
  onDone: (value: string, addedReferenceIds: string[]) => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(initialValue);
  const [added, setAdded] = useState<
    Array<PromptRichToken & { candidateId: string }>
  >([]);
  const editorRef = useRef<PromptTokenEditorHandle>(null);
  useEffect(() => {
    if (!open) return;
    setDraft(initialValue);
    setAdded([]);
    // initialValue is sampled when the modal opens; edits stay local.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const allTokens = [...tokens, ...added];
  const addedIds = new Set(added.map((token) => token.candidateId));
  const openCandidates = candidates.filter(
    (candidate) => !addedIds.has(candidate.id),
  );
  const addCandidate = (candidate: PromptRefCandidate) => {
    const index =
      allTokens.reduce((max, token) => Math.max(max, token.index), 0) + 1;
    setAdded((previous) => [
      ...previous,
      {
        candidateId: candidate.id,
        index,
        name: candidate.name,
        kind: "artifact",
        thumbUrl: candidate.thumbUrl,
      },
    ]);
    // The editor reads tokens through a ref updated on render; defer the
    // insert one frame so the new token is resolvable.
    requestAnimationFrame(() => editorRef.current?.insertToken(index));
  };

  const referenceEntry = (
    key: string,
    index: number,
    name: string,
    thumbUrl: string | null,
    onClick: () => void,
    badge?: string,
  ) => (
    <button
      key={key}
      type="button"
      onClick={onClick}
      className="mb-1.5 flex w-full items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-2 py-1.5 text-left transition-colors hover:border-[var(--color-accent)]"
    >
      {thumbUrl ? (
        <img
          src={thumbUrl}
          alt=""
          className="h-6 w-8 rounded border border-[var(--color-border)] object-cover"
        />
      ) : (
        <span className="flex h-6 w-8 items-center justify-center rounded border border-dashed border-[var(--color-border)] font-mono text-[8px] text-[var(--color-text-tertiary)]">
          {badge ?? index}
        </span>
      )}
      <span className="min-w-0 flex-1 truncate text-[10.5px]">
        <b className="font-mono text-[9px] text-[var(--color-accent)]">
          {badge ?? `[${index}]`}
        </b>{" "}
        {name}
      </span>
    </button>
  );

  return (
    <Modal
      open={open}
      onCancel={onCancel}
      width="min(960px, 94vw)"
      title={
        <span className="text-sm font-bold">
          {t("r2v.fullscreenEditTitle", { label })}
          <span className="ml-2 text-[11px] font-normal text-[var(--color-text-tertiary)]">
            {t("r2v.promptChars", {
              count: draft.replace(/\s/g, "").length,
            })}
          </span>
        </span>
      }
      footer={
        <div className="flex justify-end gap-2">
          <Button size="small" onClick={onCancel}>
            {t("r2v.fullscreenCancel")}
          </Button>
          <Button
            size="small"
            type="primary"
            disabled={disabled}
            data-prompt-editor-done
            onClick={() =>
              onDone(
                draft,
                added.map((token) => token.candidateId),
              )
            }
          >
            {t("r2v.fullscreenDone")}
          </Button>
        </div>
      }
      destroyOnHidden
    >
      <div className="flex min-h-0 gap-3">
        <PromptTokenEditor
          ref={editorRef}
          initialValue={initialValue}
          tokens={allTokens}
          disabled={disabled}
          onChange={setDraft}
        />
        {(allTokens.length > 0 || openCandidates.length > 0) && (
          <div className="w-[210px] shrink-0 self-stretch overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-2.5">
            <p className="text-[10.5px] font-bold text-[var(--color-text-secondary)]">
              {t("r2v.insertRefTitle")}
            </p>
            <p className="mb-2 mt-0.5 text-[9.5px] leading-relaxed text-[var(--color-text-tertiary)]">
              {t("r2v.insertRefHint")}
            </p>
            {allTokens.map((token) =>
              referenceEntry(
                `token-${token.index}`,
                token.index,
                token.name,
                token.thumbUrl,
                () => editorRef.current?.insertToken(token.index),
              ),
            )}
            {openCandidates.length > 0 && (
              <p className="mb-1.5 mt-3 text-[10.5px] font-bold text-[var(--color-text-secondary)]">
                {t("r2v.addableRefTitle")}
              </p>
            )}
            {openCandidates.map((candidate) =>
              referenceEntry(
                `candidate-${candidate.id}`,
                0,
                candidate.name,
                candidate.thumbUrl,
                () => addCandidate(candidate),
                "+",
              ),
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
