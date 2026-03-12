import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { Layout } from './components/layout/Layout';
import { DashboardPage } from './pages/DashboardPage';
import { Loader2 } from 'lucide-react';

const ChatPageFallback = () => (
  <div className="flex items-center justify-center h-full">
    <div className="text-center">
      <h2 className="text-xl font-semibold text-slate-300 mb-2">Chat Page</h2>
      <p className="text-slate-400">This page is being built by Oracle</p>
    </div>
  </div>
);

const KnowledgeExplorerFallback = () => (
  <div className="flex items-center justify-center h-full">
    <div className="text-center">
      <h2 className="text-xl font-semibold text-slate-300 mb-2">
        Knowledge Explorer
      </h2>
      <p className="text-slate-400">This page is being built by Oracle</p>
    </div>
  </div>
);

const ChatPage = lazy(() =>
  import('./pages/ChatPage').catch(() => ({
    default: ChatPageFallback,
  }))
);

const KnowledgeExplorerPage = lazy(() =>
  import('./pages/KnowledgeExplorerPage').catch(() => ({
    default: KnowledgeExplorerFallback,
  }))
);

function LoadingFallback() {
  return (
    <div className="flex items-center justify-center h-full">
      <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route
            path="chat"
            element={
              <Suspense fallback={<LoadingFallback />}>
                <ChatPage />
              </Suspense>
            }
          />
          <Route
            path="knowledge"
            element={
              <Suspense fallback={<LoadingFallback />}>
                <KnowledgeExplorerPage />
              </Suspense>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
