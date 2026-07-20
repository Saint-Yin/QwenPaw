import { describe, expect, it } from 'vitest';
import { matchRoutes } from 'react-router-dom';
import { CREATOR_ROUTE_OBJECTS, FORMAL_CREATOR_ROUTES } from '@/app/router';
import { normalizeCreatorRoute } from '@/routing/navigation';

function terminalRouteId(path: string): string | undefined {
  const matches = matchRoutes(CREATOR_ROUTE_OBJECTS, path);
  return matches?.at(-1)?.route.id;
}

describe('Creator hash router', () => {
  it('registers the five formal Creator page paths', () => {
    expect(FORMAL_CREATOR_ROUTES).toEqual([
      '/',
      '/project/:id/plan',
      '/project/:id/plan/unit/:unitId/workbench',
      '/project/:id/plan/section/:sectionId',
      '/project/:id/assets',
    ]);
    expect(terminalRouteId('/')).toBe('home');
    expect(terminalRouteId('/project/p1/plan')).toBe('project-plan');
    expect(terminalRouteId('/project/p1/plan/unit/u1/workbench')).toBe('project-unit-workbench');
    expect(terminalRouteId('/project/p1/plan/section/s1')).toBe('project-section-compose');
    expect(terminalRouteId('/project/p1/assets')).toBe('project-assets');
  });

  it('keeps /project/:id as the sole project default entry', () => {
    expect(terminalRouteId('/project/p1')).toBe('project-default');
  });

  it('normalizes only safe same-app routes for host URL synchronization', () => {
    expect(normalizeCreatorRoute('/project/p1/plan?reviewOp=op-1')).toBe('/project/p1/plan?reviewOp=op-1');
    expect(normalizeCreatorRoute('/')).toBe('/');
    expect(normalizeCreatorRoute('project/p1/plan')).toBeNull();
    expect(normalizeCreatorRoute('//example.com/project/p1/plan')).toBeNull();
    expect(normalizeCreatorRoute('/project/p1/plan#other')).toBeNull();
  });

  it.each([
    '/project/p1/script',
    '/project/p1/video',
    '/project/p1/edit/episode-1',
    '/project/p1/canvas',
    '/project/p1/canvas/asset-canvas',
  ])('does not register or redirect removed route %s', (path) => {
    expect(terminalRouteId(path)).toBe('project-not-found');
  });
});
