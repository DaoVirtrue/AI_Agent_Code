import { Layout, Breadcrumb, Button, Dropdown, Avatar, Space, theme as antTheme } from 'antd';
import type { MenuProps } from 'antd';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SunOutlined,
  MoonOutlined,
  UserOutlined,
  LogoutOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useAppStore, useAuthStore } from '@/store';
import { useNavigate } from 'react-router-dom';
import { useCallback } from 'react';

const { Header } = Layout;

export function DashboardHeader() {
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const breadcrumbs = useAppStore((s) => s.breadcrumbs);
  const theme = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const { token: antToken } = antTheme.useToken();

  const handleLogout = useCallback(async () => {
    await logout();
    navigate('/login');
  }, [logout, navigate]);

  const dropdownItems: MenuProps['items'] = [
    {
      key: 'user-info',
      label: (
        <div className="px-1 py-1">
          <div className="font-medium text-sm">{user?.username || '用户'}</div>
          <div className="text-xs text-gray-400">{user?.role || '访客'}</div>
        </div>
      ),
      disabled: true,
    },
    { type: 'divider' },
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: '系统设置',
      onClick: () => navigate('/admin'),
    },
    { type: 'divider' },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
      danger: true,
    },
  ];

  const breadcrumbItems = breadcrumbs.map((item, index) => ({
    title: item.path ? (
      <a onClick={() => navigate(item.path!)} className="cursor-pointer">
        {item.title}
      </a>
    ) : (
      item.title
    ),
    key: index,
  }));

  return (
    <Header
      className="flex items-center justify-between px-4 border-b border-gray-200 dark:border-gray-700"
      style={{
        background: antToken.colorBgContainer,
        padding: '0 16px',
        height: 64,
        lineHeight: '64px',
      }}
    >
      {/* Left section */}
      <div className="flex items-center gap-3">
        <Button
          type="text"
          icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={toggleSidebar}
          className="text-lg"
        />
        <Breadcrumb items={breadcrumbItems} className="hidden sm:block" />
      </div>

      {/* Right section */}
      <Space size="middle">
        <Button
          type="text"
          icon={theme === 'dark' ? <SunOutlined /> : <MoonOutlined />}
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          title={theme === 'dark' ? '切换日间模式' : '切换夜间模式'}
        />
        <Dropdown menu={{ items: dropdownItems }} placement="bottomRight" trigger={['click']}>
          <Avatar
            icon={<UserOutlined />}
            className="cursor-pointer"
            style={{ backgroundColor: '#1677ff' }}
          />
        </Dropdown>
      </Space>
    </Header>
  );
}
