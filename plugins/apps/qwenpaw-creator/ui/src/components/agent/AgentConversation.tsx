import { useMemo } from "react";
import { Plus, Send, Square } from "lucide-react";
import { message } from "antd";
import { interruptCreator } from "@/api/creator";
import { useCreatorSessionStore } from "@/store/creatorSessionStore";
import { useAgentDockUiStore } from "@/store/agentDockUiStore";
import { useCreatorInteractionStore } from "@/store/creatorInteractionStore";
import MentionInput from "./MentionInput";
import { getAssetVersionMediaUrl, getGeneratedMediaUrl } from "@/api/creator";
import {
  conversationContent,
  shouldRenderConversationMessage,
} from "@/lib/creatorMessagePresentation";

function messageMediaUrl(rawUrl: string, assetVersionRef?: string): string {
  return assetVersionRef?.startsWith("asset-version:")
    ? getAssetVersionMediaUrl(assetVersionRef.slice("asset-version:".length))
    : getGeneratedMediaUrl(rawUrl);
}

function MessageContent({
  content,
}: {
  content: import("@/contracts/creator").CreatorContentPart[];
}) {
  return (
    <>
      {content.map((part, index) => {
        if (part.type === "text")
          return (
            <span key={index} className="whitespace-pre-wrap">
              {part.text}
            </span>
          );
        if (part.type === "image_url")
          return (
            <img
              key={index}
              src={messageMediaUrl(
                part.image_url.url,
                part.attachment?.assetVersionRef,
              )}
              alt="消息图片"
              className="mt-1 max-h-40 rounded object-contain"
            />
          );
        if (part.type === "video_url")
          return (
            <video
              key={index}
              src={messageMediaUrl(
                part.video_url.url,
                part.attachment?.assetVersionRef,
              )}
              controls
              preload="metadata"
              className="mt-1 max-h-40 rounded"
            />
          );
        return (
          <span
            key={index}
            className="mt-1 block rounded bg-black/5 px-2 py-1 text-[10px]"
          >
            {part.type} ·{" "}
            {String(part.attachment.name || part.attachment.filename || "附件")}
          </span>
        );
      })}
    </>
  );
}

export default function AgentConversation({
  projectId,
}: {
  projectId: string;
}) {
  const conversations = useCreatorSessionStore((state) => state.conversations);
  const activeConversationId = useCreatorSessionStore(
    (state) => state.activeConversationId,
  );
  const messages = useCreatorSessionStore((state) => state.messages);
  const queued = useCreatorSessionStore((state) => state.queuedUi);
  const hasMoreMessages = useCreatorSessionStore(
    (state) => state.hasMoreMessages,
  );
  const setConversation = useCreatorSessionStore(
    (state) => state.setConversation,
  );
  const newConversation = useCreatorSessionStore(
    (state) => state.newConversation,
  );
  const loadOlder = useCreatorSessionStore((state) => state.loadOlderMessages);
  const sendMessage = useCreatorSessionStore((state) => state.sendMessage);
  const draft = useAgentDockUiStore((state) => state.draft);
  const selection = useAgentDockUiStore((state) => state.selection);
  const setDraft = useAgentDockUiStore((state) => state.setDraft);
  const setSelection = useAgentDockUiStore((state) => state.setSelection);
  const context = useCreatorInteractionStore();
  const extraRefs = useCreatorInteractionStore((state) => state.extraRefs);
  const canSend = Boolean(draft.trim());
  const ordered = useMemo(
    () =>
      [...messages]
        .filter(shouldRenderConversationMessage)
        .sort((a, b) => a.messageSeq - b.messageSeq),
    [messages],
  );

  const submit = async () => {
    if (!canSend) return;
    const value = draft.trim();
    try {
      await sendMessage({
        message: value,
        context: {
          panel: context.panel,
          selected: context.selectedRef
            ? { ref: context.selectedRef }
            : undefined,
          editingField: context.editingField,
          selection: selection
            ? {
                field: selection.field,
                path: selection.path,
                ref: selection.ref,
                label: selection.label,
                text: selection.text,
                start: selection.start,
                end: selection.end,
              }
            : undefined,
          extraRefs: extraRefs.map((item) => item.ref),
        },
      });
      setDraft("");
      setSelection(null);
      useCreatorInteractionStore.getState().setSelection(null);
      useCreatorInteractionStore.getState().setExtraRefs([]);
    } catch (error) {
      message.error((error as Error).message);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b border-[var(--color-border)] p-2">
        <select
          value={activeConversationId || ""}
          onChange={(event) =>
            void setConversation(event.target.value).catch((error) =>
              message.error((error as Error).message),
            )
          }
          className="min-w-0 flex-1 rounded border border-[var(--color-border)] bg-white px-2 py-1 text-[11px]"
        >
          {conversations.map((item, index) => (
            <option key={item.conversationId} value={item.conversationId}>
              {item.title || `对话 ${conversations.length - index}`}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-label="新对话"
          onClick={() =>
            void newConversation().catch((error) =>
              message.error((error as Error).message),
            )
          }
          className="icon-button !h-7 !w-7"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          aria-label="停止"
          onClick={() =>
            void interruptCreator(projectId)
              .then(() => message.success("已请求停止"))
              .catch((error) => message.error((error as Error).message))
          }
          className="icon-button !h-7 !w-7"
        >
          <Square className="h-3 w-3" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {hasMoreMessages && (
          <button
            onClick={() => void loadOlder()}
            className="mb-2 w-full text-center text-[10px] text-[var(--color-text-tertiary)]"
          >
            加载更多消息
          </button>
        )}
        {ordered.map((item) => (
          <div
            key={item.messageId}
            data-agent-message
            className={`mb-2 flex ${
              item.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`max-w-[88%] whitespace-pre-wrap rounded-lg px-2.5 py-2 text-xs leading-5 ${
                item.role === "user"
                  ? "bg-[var(--color-accent)] text-white"
                  : "border border-[var(--color-border)] bg-[var(--color-bg-secondary)] text-[var(--color-text-primary)]"
              }`}
            >
              <MessageContent content={conversationContent(item)} />
            </div>
          </div>
        ))}
        {queued.map((item) => (
          <div
            key={item.clientMessageId}
            className="mb-2 ml-auto max-w-[88%] rounded-lg border border-dashed border-[var(--color-accent)] bg-[var(--color-accent-soft)] px-2.5 py-2 text-xs"
          >
            <div>{item.text}</div>
            <div className="mt-1 text-[10px] text-[var(--color-text-tertiary)]">
              {item.state === "failed" ? item.error : "已持久化，等待消息边界"}
            </div>
          </div>
        ))}
      </div>
      <div
        data-agent-composer
        className="border-t border-[var(--color-border)] p-2"
      >
        {extraRefs.length > 0 && (
          <div className="mb-1 flex flex-wrap gap-1">
            {extraRefs.map((ref) => (
              <span
                key={ref.ref}
                className="rounded bg-[var(--color-bg-secondary)] px-1.5 py-0.5 text-[10px]"
              >
                @{ref.name}
              </span>
            ))}
          </div>
        )}
        <MentionInput
          projectId={projectId}
          value={draft}
          selection={selection}
          onChange={setDraft}
          onSelectionChange={(value) => {
            setSelection(value);
            useCreatorInteractionStore.getState().setSelection(value);
          }}
          onAddRef={(ref) => {
            setDraft(draft.replace(/(?:^|\s)@[^\s@]*$/, "").trimEnd());
            useCreatorInteractionStore
              .getState()
              .setExtraRefs([
                ...extraRefs.filter((item) => item.ref !== ref.ref),
                ref,
              ]);
          }}
          onSubmit={() => void submit()}
        />
        <div className="mt-1.5 flex items-center justify-between text-[10px] text-[var(--color-text-tertiary)]">
          <span>同一 Creator Session · Enter 发送</span>
          <button
            type="button"
            disabled={!canSend}
            onClick={() => void submit()}
            className="inline-flex items-center gap-1 rounded bg-[var(--color-accent)] px-2 py-1 font-semibold text-white disabled:opacity-40"
          >
            <Send className="h-3 w-3" />
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
