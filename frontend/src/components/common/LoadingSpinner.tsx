import { Spin } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';

interface LoadingSpinnerProps {
  tip?: string;
  fullScreen?: boolean;
  size?: 'small' | 'default' | 'large';
}

export function LoadingSpinner({ tip = '加载中...', fullScreen = true, size = 'large' }: LoadingSpinnerProps) {
  const containerStyle: React.CSSProperties = fullScreen
    ? {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        width: '100vw',
        position: 'fixed',
        top: 0,
        left: 0,
        zIndex: 9999,
        background: 'rgba(255,255,255,0.8)',
      }
    : {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 0',
        width: '100%',
      };

  return (
    <div style={containerStyle}>
      <Spin
        indicator={<LoadingOutlined style={{ fontSize: size === 'large' ? 48 : size === 'small' ? 20 : 32 }} spin />}
        tip={tip}
        size={size}
      >
        <div style={{ padding: 50 }} />
      </Spin>
    </div>
  );
}
