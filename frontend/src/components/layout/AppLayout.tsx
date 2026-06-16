import { Layout } from 'antd';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { DashboardHeader } from './Header';
import { useAppStore } from '@/store';

const { Sider, Content } = Layout;

export function AppLayout() {
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useAppStore((s) => s.setSidebarCollapsed);
  const theme = useAppStore((s) => s.theme);

  return (
    <Layout className="h-screen overflow-hidden">
      <Sider
        collapsible
        collapsed={sidebarCollapsed}
        onCollapse={setSidebarCollapsed}
        trigger={null}
        width={240}
        collapsedWidth={80}
        theme={theme === 'dark' ? 'dark' : 'light'}
        className="border-r border-gray-200 dark:border-gray-700"
      >
        <Sidebar />
      </Sider>
      <Layout>
        <DashboardHeader />
        <Content
          className="overflow-auto"
          style={{
            padding: 24,
            background: theme === 'dark' ? '#0d1117' : '#f5f5f5',
            minHeight: 0,
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
