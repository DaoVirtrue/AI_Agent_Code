import { Menu } from 'antd';
import type { MenuProps } from 'antd';
import {
  DashboardOutlined,
  MessageOutlined,
  DatabaseOutlined,
  RobotOutlined,
  FileTextOutlined,
  ApiOutlined,
  LinkOutlined,
  SettingOutlined,
  TeamOutlined,
  AuditOutlined,
  KeyOutlined,
  AppstoreOutlined,
  ExperimentOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAppStore } from '@/store';
import { useMemo } from 'react';

type MenuItem = Required<MenuProps>['items'][number];

function getItem(
  label: React.ReactNode,
  key: string,
  icon?: React.ReactNode,
  children?: MenuItem[],
): MenuItem {
  return { label, key, icon, children } as MenuItem;
}

const menuItems: MenuItem[] = [
  getItem('仪表盘', '/dashboard', <DashboardOutlined />),
  getItem('AI 工作台', '/chat', <MessageOutlined />),
  getItem('RAG 知识库', '/rag', <DatabaseOutlined />),
  getItem('Agent 控制台', '/agent', <RobotOutlined />),
  getItem('智能体专家', '/experts', <UserOutlined />),
  getItem('技能仓库', '/skills', <ApiOutlined />),
  getItem('Prompt 工程', '/prompts', <FileTextOutlined />),
  getItem('网关监控', '/gateway', <ApiOutlined />),
  getItem('MCP 管理', '/mcp', <LinkOutlined />),
  getItem('质量评测', '/eval', <ExperimentOutlined />),
  getItem('系统管理', '/admin', <SettingOutlined />, [
    getItem('概览', '/admin', <AppstoreOutlined />),
    getItem('租户管理', '/admin/tenants', <TeamOutlined />),
    getItem('审计日志', '/admin/audit', <AuditOutlined />),
    getItem('API 密钥', '/admin/keys', <KeyOutlined />),
  ]),
];

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const collapsed = useAppStore((s) => s.sidebarCollapsed);
  const theme = useAppStore((s) => s.theme);

  const selectedKeys = useMemo(() => {
    const path = location.pathname;
    return [path];
  }, [location.pathname]);

  const openKeys = useMemo(() => {
    if (location.pathname.startsWith('/admin')) return ['/admin'];
    return [];
  }, [location.pathname]);

  const onClick: MenuProps['onClick'] = ({ key }) => {
    navigate(key);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Logo area */}
      <div
        className="flex items-center h-16 px-4 border-b border-gray-200 dark:border-gray-700"
        style={{ justifyContent: collapsed ? 'center' : 'flex-start' }}
      >
        <div
          className="flex items-center justify-center rounded-lg"
          style={{
            width: 40,
            height: 40,
            background: 'linear-gradient(135deg, #1677ff, #722ed1)',
          }}
        >
          <AppstoreOutlined style={{ fontSize: 20, color: '#fff' }} />
        </div>
        {!collapsed && (
          <span className="ml-3 text-lg font-bold text-gray-900 dark:text-white whitespace-nowrap">
            LLM 平台
          </span>
        )}
      </div>

      {/* Menu */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden py-2">
        <Menu
          mode="inline"
          selectedKeys={selectedKeys}
          defaultOpenKeys={openKeys}
          items={menuItems}
          onClick={onClick}
          inlineCollapsed={collapsed}
          style={{ borderInlineEnd: 'none' }}
          theme={theme === 'dark' ? 'dark' : 'light'}
        />
      </div>

      {/* Bottom version info */}
      {!collapsed && (
        <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs text-gray-400 dark:text-gray-500">LLM 平台 v1.0</p>
        </div>
      )}
    </div>
  );
}
