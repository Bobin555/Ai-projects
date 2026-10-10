import { describe, it, expect } from 'vitest';
import { parseHotspotsMd, slug, mergeHotspots } from '../src/hotspotsMd.js';

const EXAMPLE = `# Reception hotspots
Written from the site description.

## Card drop box
- Drop your visitor card here when you leave
- After 5 pm, cards must go in this box, not to reception

## Wellbeing room
- Quiet space for breaks and first aid recovery
- Ask reception for the key
`;

describe('parseHotspotsMd', () => {
  it('reads each heading and its points', () => {
    const { items, errors } = parseHotspotsMd(EXAMPLE);
    expect(errors).toEqual([]);
    expect(items).toEqual([
      { id: 'card-drop-box', title: 'Card drop box', points: ['Drop your visitor card here when you leave', 'After 5 pm, cards must go in this box, not to reception'] },
      { id: 'wellbeing-room', title: 'Wellbeing room', points: ['Quiet space for breaks and first aid recovery', 'Ask reception for the key'] },
    ]);
  });
  it('reports a hotspot with only 1 point, with its line number', () => {
    const { errors } = parseHotspotsMd('## Fire exit\n- Keep clear\n');
    expect(errors.join('\n')).toMatch(/line 1: .*Fire exit.*2-3 points/);
  });
  it('reports a hotspot with 4 points', () => {
    const { errors } = parseHotspotsMd('## Fire exit\n- a\n- b\n- c\n- d\n');
    expect(errors.join('\n')).toMatch(/line 1:/);
  });
  it('reports duplicate titles', () => {
    const { errors } = parseHotspotsMd('## Exit\n- a\n- b\n## Exit\n- c\n- d\n');
    expect(errors.join('\n')).toMatch(/line 4: .*duplicate/);
  });
  it('accepts * bullets too', () => {
    expect(parseHotspotsMd('## Exit\n* a\n* b\n').items[0].points).toEqual(['a', 'b']);
  });
});

describe('slug', () => {
  it('makes a readable id', () => {
    expect(slug('Card drop box')).toBe('card-drop-box');
    expect(slug('  First-aid kit (main)! ')).toBe('first-aid-kit-main');
  });
});

describe('mergeHotspots', () => {
  const placed = [{ id: 'card-drop-box', title: 'Old title', points: ['x', 'y'], position: [1, 0, 2], radius: 1.5 }];
  it('keeps positions by id and takes text from the file', () => {
    const { items } = parseHotspotsMd(EXAMPLE);
    expect(mergeHotspots(items, placed)).toEqual([
      { id: 'card-drop-box', title: 'Card drop box', points: items[0].points, position: [1, 0, 2], radius: 1.5 },
    ]);
  });
  it('drops placed hotspots that are no longer in the file', () => {
    expect(mergeHotspots([], placed)).toEqual([]);
  });
});
