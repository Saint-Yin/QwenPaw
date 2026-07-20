import { diffSegments } from "./ReviewFieldText";

export default function ReviewDiffText({
  before = "",
  after = "",
  field,
}: {
  before?: string;
  after?: string;
  field: string;
}) {
  const diff = diffSegments(before, after);
  return (
    <div
      data-review-diff-field={field}
      className="select-text whitespace-pre-wrap rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-2 text-[11px] leading-5"
    >
      {diff.map((segment, index) => {
        if (segment.type === "equal")
          return <span key={index}>{segment.text}</span>;
        if (segment.type === "del")
          return (
            <del key={index} className="agent-diff-del">
              {segment.text}
            </del>
          );
        return (
          <ins key={index} className="agent-diff-add no-underline">
            {segment.text}
          </ins>
        );
      })}
    </div>
  );
}
