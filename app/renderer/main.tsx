import { createRoot } from 'react-dom/client';
import './monaco-setup';
import 'reactflow/dist/style.css';
import './styles.css';
import { App } from './App';
import { ApiProvider } from './bridge/context';

const container = document.getElementById('root');
if (!container) throw new Error('missing #root element');

createRoot(container).render(
  <ApiProvider>
    <App />
  </ApiProvider>,
);
