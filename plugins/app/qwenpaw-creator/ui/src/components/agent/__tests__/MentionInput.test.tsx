import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MentionInput } from '@/components/agent';
import type { SelectionAttachment } from '@/store/agentDockUiStore';

const selection: SelectionAttachment = {
  text: '雪夜 SUV',
  ref: 'unit:u1',
  field: 'unit:u1/storyText',
  path: '/story/sections/items/s1/units/items/u1/narrative',
  start: 2,
  end: 8,
  label: '分镜文本',
};

function Harness({ initial = selection }: { initial?: SelectionAttachment | null }) {
  const [value, setValue] = useState('请修改节奏');
  const [selected, setSelected] = useState(initial);
  return <><MentionInput projectId="p1" value={value} selection={selected} onChange={setValue} onSelectionChange={setSelected} onAddRef={vi.fn()} onSubmit={vi.fn()} /><output data-testid="selection">{selected?.text || ''}</output></>;
}

describe('MentionInput inline selection structure', () => {
  it('renders the selected review text inside the editor and serializes it for copy', () => {
    render(<Harness />);
    const editor = screen.getByRole('textbox');
    expect(editor.querySelector('[data-selection-ref]')).toHaveTextContent('雪夜 SUV');
    const values: Record<string, string> = {};
    fireEvent.copy(editor, { clipboardData: { setData: (type: string, value: string) => { values[type] = value; } } });
    expect(values['text/html']).toContain('data-selection-ref');
    expect(values['text/plain']).toContain('雪夜 SUV');
    expect(decodeURIComponent(editor.querySelector<HTMLElement>('[data-selection-ref]')!.dataset.selectionRef!)).toContain(selection.path!);
  });

  it('restores the special inline reference on paste', () => {
    const { rerender } = render(<Harness initial={null} />);
    const token = encodeURIComponent(JSON.stringify(selection));
    const editor = screen.getByRole('textbox');
    fireEvent.paste(editor, { clipboardData: { getData: (type: string) => type === 'text/html' ? `<span data-selection-ref="${token}">雪夜 SUV</span>` : '' } });
    expect(screen.getByTestId('selection')).toHaveTextContent('雪夜 SUV');
    rerender(<Harness initial={selection} />);
  });
});
