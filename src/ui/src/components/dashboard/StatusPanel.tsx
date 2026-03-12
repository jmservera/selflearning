import { useEffect, useState } from 'react';
import { Activity, Brain, Database, FileText, Circle } from 'lucide-react';
import type { DashboardStatus } from '@/lib/types';
import { useWebSocket } from '@/hooks/useWebSocket';

interface StatusPanelProps {
  initialStatus: DashboardStatus | null;
}

export function StatusPanel({ initialStatus }: StatusPanelProps) {
  const [status, setStatus] = useState<DashboardStatus | null>(initialStatus);
  const [isPulsing, setIsPulsing] = useState(false);

  useWebSocket({
    path: '/ws/status',
    onMessage: (message) => {
      if (message.type === 'status_update') {
        setStatus(message.data as unknown as DashboardStatus);
        setIsPulsing(true);
        setTimeout(() => setIsPulsing(false), 1000);
      }
    },
  });

  useEffect(() => {
    if (initialStatus) {
      setStatus(initialStatus);
    }
  }, [initialStatus]);

  if (!status) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-slate-700 rounded w-1/3"></div>
          <div className="h-8 bg-slate-700 rounded"></div>
        </div>
      </div>
    );
  }

  const healthColor =
    status.system_health === 'healthy'
      ? 'text-emerald-500'
      : status.system_health === 'degraded'
      ? 'text-amber-500'
      : 'text-rose-500';

  const isActive = status.current_activity !== 'idle';

  return (
    <div className={`bg-slate-800 rounded-lg border border-slate-700 p-6 transition-all ${
      isPulsing ? 'ring-2 ring-blue-500/50' : ''
    }`}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">System Status</h2>
        <Circle className={`w-3 h-3 fill-current ${healthColor} ${isActive ? 'animate-pulse' : ''}`} />
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-400">
            <Activity className="w-4 h-4" />
            <span className="text-sm">Current Activity</span>
          </div>
          <span className={`text-sm font-medium ${isActive ? 'text-blue-400' : 'text-slate-500'}`}>
            {status.current_activity}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-400">
            <Brain className="w-4 h-4" />
            <span className="text-sm">Active Topics</span>
          </div>
          <span className="text-sm font-medium text-slate-200">{status.active_topics}</span>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-400">
            <Database className="w-4 h-4" />
            <span className="text-sm">Total Entities</span>
          </div>
          <span className="text-sm font-medium text-slate-200">
            {status.total_entities.toLocaleString()}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-400">
            <FileText className="w-4 h-4" />
            <span className="text-sm">Total Claims</span>
          </div>
          <span className="text-sm font-medium text-slate-200">
            {status.total_claims.toLocaleString()}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-400">
            <Activity className="w-4 h-4" />
            <span className="text-sm">Learning Cycles</span>
          </div>
          <span className="text-sm font-medium text-slate-200">
            {status.active_learning_cycles}
          </span>
        </div>

        {status.last_activity && (
          <div className="pt-4 border-t border-slate-700">
            <div className="text-xs text-slate-500">
              Last activity: {new Date(status.last_activity).toLocaleString()}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
