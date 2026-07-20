import type {
  CreatorScenario,
  GenerationUnitView,
  PlanView,
  SectionView,
} from '@/contracts/creator';

export interface PlanTerms {
  structure: string;
  section: string;
  unit: string;
}

export interface PlanDetailSelection {
  selectedSection: SectionView | undefined;
  selectedUnit: GenerationUnitView | undefined;
  detailOpen: boolean;
}

export function selectPlanDetail(
  view: PlanView | null,
  selectedSectionId?: string,
  selectedUnitId?: string,
): PlanDetailSelection {
  const selectedSection = view?.sections.find((section) => section.id === selectedSectionId)
    || view?.sections.find((section) => section.units.some((unit) => unit.id === selectedUnitId));
  const selectedUnit = selectedSection?.units.find((unit) => unit.id === selectedUnitId);
  return {
    selectedSection,
    selectedUnit,
    detailOpen: Boolean(selectedSection),
  };
}

export function selectPlanTotalDuration(view: PlanView | null): number {
  return view?.sections
    .flatMap((section) => section.units)
    .reduce((sum, unit) => sum + unit.duration, 0) || 0;
}

export function selectPlanTerms(scenario?: CreatorScenario): PlanTerms {
  if (scenario === 'short_drama') {
    return { structure: '剧本大纲', section: '集', unit: 'Clip' };
  }
  if (scenario === 'video_edit') {
    return { structure: '剪辑方案', section: '剪辑段', unit: '剪辑片段' };
  }
  return { structure: '视频结构', section: 'Section', unit: '生成单元' };
}
