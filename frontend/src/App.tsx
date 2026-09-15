import { Routes, Route, Navigate } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { RouteGuard } from '@/components/layout/RouteGuard';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { LoginPage } from '@/pages/LoginPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { ChatPage } from '@/pages/chat/ChatPage';

// Lazy-loaded pages for code splitting
import { lazy, Suspense } from 'react';
import { Spin } from 'antd';

const LazyLoading = () => (
  <div className="flex items-center justify-center h-full w-full min-h-[400px]">
    <Spin size="large" tip="加载中..." />
  </div>
);

const RAGPage = lazy(() => import('@/pages/RAGPage').then(m => ({ default: m.RAGPage })));
const AgentPage = lazy(() => import('@/pages/AgentPage').then(m => ({ default: m.AgentPage })));
const PromptsPage = lazy(() => import('@/pages/PromptsPage').then(m => ({ default: m.PromptsPage })));
const GatewayPage = lazy(() => import('@/pages/GatewayPage').then(m => ({ default: m.GatewayPage })));
const MCPPage = lazy(() => import('@/pages/MCPPage').then(m => ({ default: m.MCPPage })));
const EvalPage = lazy(() => import('@/pages/EvalPage').then(m => ({ default: m.EvalPage })));
const DocGenPage = lazy(() => import('@/pages/DocGenPage').then(m => ({ default: m.DocGenPage })));
const AdminPage = lazy(() => import('@/pages/AdminPage').then(m => ({ default: m.AdminPage })));

function SuspenseWrapper({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LazyLoading />}>{children}</Suspense>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RouteGuard><AppLayout /></RouteGuard>}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/rag" element={<SuspenseWrapper><RAGPage /></SuspenseWrapper>} />
          <Route path="/agent" element={<SuspenseWrapper><AgentPage /></SuspenseWrapper>} />
          <Route path="/prompts" element={<SuspenseWrapper><PromptsPage /></SuspenseWrapper>} />
          <Route path="/gateway" element={<SuspenseWrapper><GatewayPage /></SuspenseWrapper>} />
          <Route path="/mcp" element={<SuspenseWrapper><MCPPage /></SuspenseWrapper>} />
          <Route path="/eval" element={<SuspenseWrapper><EvalPage /></SuspenseWrapper>} />
          <Route path="/docs" element={<SuspenseWrapper><DocGenPage /></SuspenseWrapper>} />
          <Route path="/admin/*" element={
            <RouteGuard requiredRole="admin">
              <SuspenseWrapper><AdminPage /></SuspenseWrapper>
            </RouteGuard>
          } />
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}
