import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { LabelDesigner } from './LabelDesigner';

test('saves and reloads a formal bounded label schema', () => {
  localStorage.clear();
  const onChange = vi.fn();
  render(<LabelDesigner onChange={onChange} />);
  fireEvent.click(screen.getByRole('button', { name: '保存模板' }));
  const saved = JSON.parse(localStorage.getItem('smartorder-label-template') ?? '{}');
  expect(saved.schema_version).toBe(1);
  expect(saved.width_mm).toBe(60);
  expect(saved.height_mm).toBe(40);
  expect(saved.elements).toHaveLength(5);
  for (const element of saved.elements) {
    expect(element.x_mm + element.width_mm).toBeLessThanOrEqual(saved.width_mm);
    expect(element.y_mm + element.height_mm).toBeLessThanOrEqual(saved.height_mm);
  }
  fireEvent.click(screen.getByRole('button', { name: '重新加载' }));
  expect(onChange).toHaveBeenCalled();
});
