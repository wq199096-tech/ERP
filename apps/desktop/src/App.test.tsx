import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the Chinese product name', () => {
  render(<App />);
  expect(screen.getByText('欢迎回来')).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1, name: '智单 ERP' })).toBeInTheDocument();
});

