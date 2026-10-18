import { AppShell } from './components/AppShell';
import { LoginPage } from './components/LoginPage';
import { useAppStore } from './store';

export default function App() {
  const session = useAppStore((state) => state.session);
  return session ? <AppShell /> : <LoginPage />;
}

