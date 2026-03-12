import { Menu, Circle } from 'lucide-react';
import { useWebSocket } from '@/hooks/useWebSocket';
import type { DashboardStatus } from '@/lib/types';
import { useState } from 'react';

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const [systemHealth, setSystemHealth] = useState<string>('healthy');
  const { isConnected } = useWebSocket({
    path: '/ws/status',
    onMessage: (message) => {
      if (message.type === 'status_update') {
        const status = message.data as unknown as DashboardStatus;
        setSystemHealth(status.system_health);
      }
    },
  });

  const healthColor = systemHealth === 'healthy' ? 'text-emerald-500' : 
                      systemHealth === 'degraded' ? 'text-amber-500' : 
                      'text-rose-500';

  const connectionColor = isConnected ? 'text-emerald-500' : 'text-slate-500';

  return (
    <header className="bg-slate-900 border-b border-slate-800 px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={onMenuClick}
            className="md:hidden p-2 rounded-lg hover:bg-slate-800 transition-colors"
            aria-label="Toggle menu"
          >
            <Menu className="w-5 h-5" />
          </button>
          
          <div className="flex items-center gap-2">
            <Circle className={`w-2 h-2 fill-current ${healthColor}`} />
            <span className="text-sm text-slate-400">
              System: <span className={healthColor}>{systemHealth}</span>
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Circle className={`w-2 h-2 fill-current ${connectionColor}`} />
            <span className="text-sm text-slate-400">
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
