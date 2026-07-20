import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SectionDetail from '@/components/plan/SectionDetail';
import { planView } from '@/test/creatorFixtures';
import { useReviewManifestStore } from '@/store/reviewManifestStore';

describe('SectionDetail explicit feedback behavior', () => {
  beforeEach(() => useReviewManifestStore.getState().reset());

  it('groups inherited constraints into one cohesive editable list', () => {
    render(
      <SectionDetail
        projectId="p1"
        section={{
          ...planView.sections[0],
          constraints: ['保持角色服装一致', '夜景光线方向不变'],
        }}
        onPatch={vi.fn()}
        onSelectUnit={vi.fn()}
        onRegenerateUnits={vi.fn()}
        regenerating={false}
      />,
    );

    const list = document.querySelector<HTMLElement>('[data-section-constraints-list]')!;
    expect(list).toHaveClass(
      'divide-y',
      'overflow-hidden',
      'rounded-lg',
      'border',
      'bg-[var(--color-bg-secondary)]/40',
    );
    expect(screen.getByDisplayValue('保持角色服装一致')).toHaveClass('!bg-transparent', '!shadow-none');
    expect(screen.getByDisplayValue('夜景光线方向不变')).toBeInTheDocument();
    expect(within(list).getByText('01')).toBeInTheDocument();
    expect(within(list).getByText('02')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '删除约束 1' })).toBeInTheDocument();
    expect(screen.getByText('段落级约束会统一传递给下属生成单元。')).toBeInTheDocument();
  });
});
