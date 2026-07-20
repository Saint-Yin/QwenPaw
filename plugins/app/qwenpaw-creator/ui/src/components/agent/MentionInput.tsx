import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import type {
  ClipboardEvent as ReactClipboardEvent,
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent as ReactMouseEvent,
} from 'react';
import { searchRefs } from '@/api/creator';
import type { RefSearchItem } from '@/contracts/creator';
import type { SelectionAttachment } from '@/store/agentDockUiStore';

export interface MentionRef {
  ref: string;
  name: string;
  type?: string;
}

export interface MentionInputHandle {
  getContent: () => {
    text: string;
    refs: MentionRef[];
    selections: SelectionAttachment[];
  };
  insertMention: (obj: MentionRef) => void;
  insertSelection: (selection: SelectionAttachment) => void;
  clear: () => void;
  clearMentions: () => void;
  focus: () => void;
  setText: (text: string) => void;
  prefillMention: (lead: string, mention: MentionRef | null, trail: string) => void;
}

interface MentionInputProps {
  placeholder?: string;
  disabled?: boolean;
  onQueryChange?: (query: string | null) => void;
  onSubmit?: () => void;
  onChange?: (value: string) => void;
  mentionOpen?: boolean;
  onMentionNavigate?: (direction: 1 | -1) => void;
  onMentionConfirm?: () => void;
  onMentionClose?: () => void;
  /** Compatibility props for consumers that still let the input own ref lookup. */
  projectId?: string;
  value?: string;
  selection?: SelectionAttachment | null;
  onSelectionChange?: (selection: SelectionAttachment | null) => void;
  onAddRef?: (ref: RefSearchItem) => void;
}

// Kept as complete literals so Tailwind includes classes injected into the editor DOM.
const PILL_CLASS =
  'mention-pill inline-block cursor-pointer rounded bg-[var(--color-accent-soft)] px-1 align-baseline text-[11px] font-medium text-[var(--color-accent)] hover:text-[var(--color-danger)] hover:line-through';
const SELECTION_PILL_CLASS =
  'selection-pill inline-block cursor-pointer rounded bg-[var(--color-accent-soft)] px-1 align-baseline text-[11px] font-medium text-[var(--color-accent)] hover:text-[var(--color-danger)] hover:line-through';

function clip(text: string, limit = 24): string {
  const normalized = text.replace(/\s+/g, ' ').trim();
  return normalized.length > limit ? `${normalized.slice(0, limit)}…` : normalized;
}

function encodedSelection(selection: SelectionAttachment): string {
  return encodeURIComponent(JSON.stringify(selection));
}

function createMentionPill(obj: MentionRef): HTMLSpanElement {
  const pill = document.createElement('span');
  pill.className = PILL_CLASS;
  pill.contentEditable = 'false';
  pill.dataset.ref = obj.ref;
  pill.dataset.name = obj.name;
  if (obj.type) pill.dataset.type = obj.type;
  pill.textContent = `@${obj.name}`;
  pill.title = '点击移除引用';
  return pill;
}

function createSelectionPill(selection: SelectionAttachment): HTMLSpanElement {
  const pill = document.createElement('span');
  pill.className = SELECTION_PILL_CLASS;
  pill.contentEditable = 'false';
  pill.dataset.sel = '1';
  pill.dataset.selText = selection.text;
  pill.dataset.selLabel = selection.label;
  if (selection.ref) pill.dataset.selRef = selection.ref;
  if (selection.field) pill.dataset.selField = selection.field;
  if (selection.path) pill.dataset.selPath = selection.path;
  pill.dataset.selStart = String(selection.start);
  pill.dataset.selEnd = String(selection.end);
  // Preserve the special structure used by the cutover tests and clipboard round-trip.
  pill.dataset.selectionRef = encodedSelection(selection);
  pill.textContent = `“${clip(selection.text)}”`;
  pill.title = `引用文本 · ${selection.label}\n可复制粘贴\n${selection.text}`;
  return pill;
}

function selectionFromElement(element: HTMLElement): SelectionAttachment {
  return {
    text: element.dataset.selText ?? '',
    ref: element.dataset.selRef ?? null,
    field: element.dataset.selField ?? null,
    path: element.dataset.selPath ?? null,
    start: Number(element.dataset.selStart ?? -1),
    end: Number(element.dataset.selEnd ?? -1),
    label: element.dataset.selLabel ?? '选中文本',
  };
}

function serialize(root: HTMLElement) {
  let text = '';
  const refs: MentionRef[] = [];
  const selections: SelectionAttachment[] = [];
  const walk = (node: Node) => {
    node.childNodes.forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE) {
        text += child.textContent ?? '';
        return;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) return;
      const element = child as HTMLElement;
      if (element.dataset.ref) {
        text += `@${element.dataset.name ?? ''}`;
        refs.push({
          ref: element.dataset.ref,
          name: element.dataset.name ?? '',
          type: element.dataset.type || undefined,
        });
        return;
      }
      if (element.dataset.sel) {
        const selection = selectionFromElement(element);
        text += `「引用·${selection.label}」`;
        selections.push(selection);
        return;
      }
      if (element.tagName === 'BR') {
        text += '\n';
        return;
      }
      const block = element.tagName === 'DIV' || element.tagName === 'P';
      if (block && text && !text.endsWith('\n')) text += '\n';
      walk(element);
    });
  };
  walk(root);
  return { text: text.replace(/\u00a0/g, ' '), refs, selections };
}

const MentionInput = forwardRef<MentionInputHandle, MentionInputProps>(function MentionInput(
  {
    placeholder = '输入修改意图，@ 可引用对象…',
    disabled,
    onQueryChange,
    onSubmit,
    onChange,
    mentionOpen,
    onMentionNavigate,
    onMentionConfirm,
    onMentionClose,
    projectId,
    value,
    selection,
    onSelectionChange,
    onAddRef,
  },
  ref,
) {
  const editorRef = useRef<HTMLDivElement>(null);
  const savedRange = useRef<Range | null>(null);
  const composing = useRef(false);
  const [empty, setEmpty] = useState(true);
  const [localQuery, setLocalQuery] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<RefSearchItem[]>([]);

  const refresh = () => {
    const editor = editorRef.current;
    const content = editor ? serialize(editor) : { text: '', refs: [], selections: [] };
    setEmpty(!editor || ((editor.textContent ?? '').trim() === '' && !editor.querySelector('[data-ref], [data-sel]')));
    onChange?.(content.text);
  };

  const saveRange = () => {
    const selectionState = window.getSelection();
    if (!selectionState || selectionState.rangeCount === 0) return;
    const range = selectionState.getRangeAt(0);
    if (editorRef.current?.contains(range.commonAncestorContainer)) {
      savedRange.current = range.cloneRange();
    }
  };

  const detectQuery = () => {
    if (composing.current) return;
    const selectionState = window.getSelection();
    if (!selectionState || selectionState.rangeCount === 0 || !selectionState.isCollapsed) {
      onQueryChange?.(null);
      setLocalQuery(null);
      return;
    }
    const range = selectionState.getRangeAt(0);
    const node = range.startContainer;
    if (!editorRef.current?.contains(node) || node.nodeType !== Node.TEXT_NODE) {
      onQueryChange?.(null);
      setLocalQuery(null);
      return;
    }
    const before = (node.textContent ?? '').slice(0, range.startOffset);
    const match = /@([^\s@]*)$/.exec(before);
    const next = match ? match[1] : null;
    onQueryChange?.(next);
    setLocalQuery(projectId && !onQueryChange ? next : null);
  };

  useEffect(() => {
    if (!projectId || localQuery === null || !onAddRef) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void searchRefs(projectId, localQuery)
        .then((result) => { if (!cancelled) setSuggestions(result.items); })
        .catch(() => { if (!cancelled) setSuggestions([]); });
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [localQuery, onAddRef, projectId]);

  // Compatibility controlled mode. AgentDock itself uses the imperative rich-text API.
  useEffect(() => {
    if (value === undefined && !selection) return;
    const editor = editorRef.current;
    if (!editor || document.activeElement === editor) return;
    editor.innerHTML = '';
    if (selection) {
      editor.append(createSelectionPill(selection), document.createTextNode('\u00a0'));
    }
    if (value) editor.append(document.createTextNode(value));
    setEmpty(!value && !selection);
  }, [selection, value]);

  const currentInsertionRange = (): Range | null => {
    const editor = editorRef.current;
    if (!editor) return null;
    editor.focus();
    const selectionState = window.getSelection();
    if (selectionState?.rangeCount && editor.contains(selectionState.getRangeAt(0).commonAncestorContainer)) {
      return selectionState.getRangeAt(0);
    }
    if (savedRange.current && editor.contains(savedRange.current.commonAncestorContainer)) {
      return savedRange.current;
    }
    const range = document.createRange();
    range.selectNodeContents(editor);
    range.collapse(false);
    return range;
  };

  const insertFragmentAtCaret = (fragment: DocumentFragment | Node) => {
    const range = currentInsertionRange();
    if (!range) return;
    range.deleteContents();
    const last = fragment instanceof DocumentFragment ? fragment.lastChild : fragment;
    range.insertNode(fragment);
    const after = document.createRange();
    if (last) after.setStartAfter(last);
    else after.selectNodeContents(editorRef.current!);
    after.collapse(true);
    const selectionState = window.getSelection();
    selectionState?.removeAllRanges();
    selectionState?.addRange(after);
    savedRange.current = after.cloneRange();
  };

  const selectedSelectionPills = (): HTMLElement[] => {
    const editor = editorRef.current;
    const selectionState = window.getSelection();
    if (!editor || !selectionState || selectionState.rangeCount === 0) return [];
    const range = selectionState.getRangeAt(0);
    if (!editor.contains(range.commonAncestorContainer)) return [];
    const wrapper = document.createElement('div');
    wrapper.appendChild(range.cloneContents());
    return Array.from(wrapper.querySelectorAll<HTMLElement>('[data-sel]'));
  };

  const fragmentFromClipboard = (event: ReactClipboardEvent<HTMLDivElement>): DocumentFragment | null => {
    const custom = event.clipboardData.getData('application/x-qwenpaw-selection-ref');
    try {
      const parsed = custom ? JSON.parse(custom) as SelectionAttachment[] | SelectionAttachment : null;
      const selections = parsed ? (Array.isArray(parsed) ? parsed : [parsed]) : [];
      if (selections.length) {
        const fragment = document.createDocumentFragment();
        selections.forEach((item, index) => {
          if (index) fragment.append(document.createTextNode('\u00a0'));
          fragment.append(createSelectionPill(item));
        });
        return fragment;
      }
    } catch {
      // Fall through to the HTML representation.
    }
    const html = event.clipboardData.getData('text/html');
    if (!html.includes('data-selection-ref') && !html.includes('data-sel')) return null;
    const documentValue = new DOMParser().parseFromString(html, 'text/html');
    const fragment = document.createDocumentFragment();
    documentValue.body.querySelectorAll<HTMLElement>('[data-selection-ref], [data-sel]').forEach((element, index) => {
      let restored: SelectionAttachment | null = null;
      if (element.dataset.sel) restored = selectionFromElement(element);
      else if (element.dataset.selectionRef) {
        try { restored = JSON.parse(decodeURIComponent(element.dataset.selectionRef)) as SelectionAttachment; } catch { restored = null; }
      }
      if (!restored) return;
      if (index) fragment.append(document.createTextNode('\u00a0'));
      fragment.append(createSelectionPill(restored));
      onSelectionChange?.(restored);
    });
    return fragment.childNodes.length ? fragment : null;
  };

  const handleCopy = (event: ReactClipboardEvent<HTMLDivElement>) => {
    const pills = selectedSelectionPills();
    if (!pills.length && selection) pills.push(createSelectionPill(selection));
    if (!pills.length) return;
    const selections = pills.map(selectionFromElement);
    const wrapper = document.createElement('div');
    pills.forEach((pill, index) => {
      if (index) wrapper.append(document.createTextNode(' '));
      wrapper.append(pill.cloneNode(true));
    });
    event.clipboardData.setData('application/x-qwenpaw-selection-ref', JSON.stringify(selections));
    event.clipboardData.setData('text/html', wrapper.innerHTML);
    event.clipboardData.setData('text/plain', selections.map((item) => item.text).join(' '));
    event.preventDefault();
  };

  const handlePaste = (event: ReactClipboardEvent<HTMLDivElement>) => {
    event.preventDefault();
    const fragment = fragmentFromClipboard(event);
    if (fragment) insertFragmentAtCaret(fragment);
    else {
      const text = event.clipboardData.getData('text/plain');
      if (text) document.execCommand('insertText', false, text);
    }
    saveRange();
    refresh();
  };

  const handleClick = (event: ReactMouseEvent<HTMLDivElement>) => {
    const pill = (event.target as HTMLElement).closest?.('[data-ref], [data-sel]');
    if (pill && editorRef.current?.contains(pill)) {
      pill.remove();
      onSelectionChange?.(null);
      refresh();
    }
    saveRange();
  };

  useImperativeHandle(ref, () => ({
    getContent: () => editorRef.current
      ? serialize(editorRef.current)
      : { text: '', refs: [], selections: [] },
    insertMention: (obj) => {
      const editor = editorRef.current;
      if (!editor) return;
      const range = currentInsertionRange();
      if (!range) return;
      const node = range.startContainer;
      if (node.nodeType === Node.TEXT_NODE) {
        const offset = range.startOffset;
        const before = (node.textContent ?? '').slice(0, offset);
        const match = /@([^\s@]*)$/.exec(before);
        if (match) {
          range.setStart(node, match.index);
          range.setEnd(node, offset);
          range.deleteContents();
        }
      }
      const pill = createMentionPill(obj);
      range.insertNode(pill);
      const space = document.createTextNode('\u00a0');
      pill.after(space);
      const after = document.createRange();
      after.setStartAfter(space);
      after.collapse(true);
      const selectionState = window.getSelection();
      selectionState?.removeAllRanges();
      selectionState?.addRange(after);
      savedRange.current = after.cloneRange();
      onQueryChange?.(null);
      setLocalQuery(null);
      setSuggestions([]);
      refresh();
    },
    insertSelection: (selectionValue) => {
      const fragment = document.createDocumentFragment();
      fragment.append(createSelectionPill(selectionValue), document.createTextNode('\u00a0'));
      insertFragmentAtCaret(fragment);
      refresh();
    },
    clear: () => {
      if (editorRef.current) editorRef.current.innerHTML = '';
      savedRange.current = null;
      setSuggestions([]);
      refresh();
    },
    clearMentions: () => {
      editorRef.current?.querySelectorAll('[data-ref], [data-sel]').forEach((element) => element.remove());
      onSelectionChange?.(null);
      refresh();
    },
    focus: () => editorRef.current?.focus(),
    setText: (text) => {
      const editor = editorRef.current;
      if (!editor) return;
      editor.textContent = text;
      editor.focus();
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(false);
      const selectionState = window.getSelection();
      selectionState?.removeAllRanges();
      selectionState?.addRange(range);
      savedRange.current = range.cloneRange();
      refresh();
    },
    prefillMention: (lead, mention, trail) => {
      const editor = editorRef.current;
      if (!editor) return;
      editor.innerHTML = '';
      if (lead) editor.append(document.createTextNode(lead));
      if (mention) editor.append(createMentionPill(mention));
      editor.append(document.createTextNode(trail || '\u00a0'));
      editor.focus();
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(false);
      const selectionState = window.getSelection();
      selectionState?.removeAllRanges();
      selectionState?.addRange(range);
      savedRange.current = range.cloneRange();
      refresh();
    },
  }));

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.nativeEvent.isComposing || composing.current) return;
    const autocompleteOpen = mentionOpen || suggestions.length > 0;
    if (autocompleteOpen && mentionOpen) {
      if (event.key === 'ArrowDown') { event.preventDefault(); onMentionNavigate?.(1); return; }
      if (event.key === 'ArrowUp') { event.preventDefault(); onMentionNavigate?.(-1); return; }
      if (event.key === 'Enter' || event.key === 'Tab') { event.preventDefault(); onMentionConfirm?.(); return; }
      if (event.key === 'Escape') { event.preventDefault(); onMentionClose?.(); return; }
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      onSubmit?.();
    }
  };

  return (
    <div className="relative min-w-0 flex-1">
      <div
        ref={editorRef}
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-label={placeholder}
        onInput={() => { saveRange(); detectQuery(); refresh(); }}
        onKeyDown={handleKeyDown}
        onKeyUp={() => { saveRange(); detectQuery(); }}
        onCompositionStart={() => { composing.current = true; }}
        onCompositionEnd={() => { composing.current = false; saveRange(); detectQuery(); refresh(); }}
        onPaste={handlePaste}
        onCopy={handleCopy}
        onMouseUp={saveRange}
        onClick={handleClick}
        onBlur={saveRange}
        className="max-h-24 min-h-[32px] w-full overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)] px-2.5 py-1.5 text-xs leading-6 text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
      />
      {empty && (
        <span className="pointer-events-none absolute left-2.5 top-1.5 text-xs leading-6 text-[var(--color-text-tertiary)]">
          {placeholder}
        </span>
      )}
      {suggestions.length > 0 && onAddRef && (
        <div className="absolute bottom-full left-0 right-0 z-20 mb-1 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-lg">
          {suggestions.map((item) => (
            <button
              key={item.ref}
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                onAddRef(item);
                setSuggestions([]);
                setLocalQuery(null);
              }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-[var(--color-accent-soft)]"
            >
              <span className="rounded bg-[var(--color-bg-secondary)] px-1 text-[10px] text-[var(--color-text-tertiary)]">{item.type}</span>
              <span className="truncate text-[var(--color-text-primary)]">{item.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
});

export default MentionInput;
