import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import UnitDetail from '@/components/plan/UnitDetail';
import { editView, planView, unit } from '@/test/creatorFixtures';
import { useReviewManifestStore } from '@/store/reviewManifestStore';

describe('UnitDetail latest origin/main behavior', () => {
  beforeEach(() => useReviewManifestStore.getState().reset());

  it('keeps the origin storyboard retry affordance when the selected image cannot load', () => {
    render(
      <UnitDetail
        projectId="p1"
        section={planView.sections[0]}
        unit={{ ...unit, storyboardImageUrl: '/generated/missing-storyboard.png' }}
      />,
    );

    fireEvent.error(screen.getByAltText('分镜图'));
    expect(screen.getByText('分镜图加载失败，可在工作台重新生成')).toBeInTheDocument();
    expect(screen.queryByAltText('分镜图')).not.toBeInTheDocument();
  });

  it('streams a selected storyboard file artifact through its version route', () => {
    render(
      <UnitDetail
        projectId="p1"
        section={planView.sections[0]}
        unit={{
          ...unit,
          storyboardImageUrl: 'file:///private/runtime/storyboard.png',
          storyboardImageVersionId: 'storyboard-v1',
        }}
      />,
    );

    expect(screen.getByAltText('分镜图')).toHaveAttribute(
      'src',
      '/api/creator/media/artifacts/storyboard-v1',
    );
  });

  it('shows the AI edit summary and VLM storyboard content in the plan detail', () => {
    const { container } = render(
      <UnitDetail
        projectId="p1"
        section={planView.sections[0]}
        unit={{ ...unit, taskType: 'edit' }}
        editWorkbench={{
          ...editView,
          storyboard_image_url: '/generated/edit-storyboard.svg',
        }}
      />,
    );

    expect(screen.getByText('VLM 关键帧分镜')).toBeInTheDocument();
    expect(screen.getAllByText('剪辑摘要')).toHaveLength(2);
    expect(screen.getByText('源视频关键帧')).toBeInTheDocument();
    expect(screen.queryByAltText('VLM 关键帧分镜图')).not.toBeInTheDocument();
    expect(container.querySelector('[data-creator-field="unit:u1/editPlan/storyboard/panel:panel-1/description"]')).toHaveAttribute(
      'data-creator-path',
      '/production/units_by_id/u1/plan/storyboard/items/panel-1/description',
    );
  });
});
