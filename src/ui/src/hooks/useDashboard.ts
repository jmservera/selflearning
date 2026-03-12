import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import type {
  DashboardStatus,
  LearningProgress,
  ActivityLog,
  DecisionLog,
} from '@/lib/types';

interface UseDashboardReturn {
  status: DashboardStatus | null;
  progress: LearningProgress | null;
  logs: ActivityLog[];
  decisions: DecisionLog[];
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useDashboard(autoRefreshMs = 5000): UseDashboardReturn {
  const [status, setStatus] = useState<DashboardStatus | null>(null);
  const [progress, setProgress] = useState<LearningProgress | null>(null);
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [decisions, setDecisions] = useState<DecisionLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [statusData, progressData, logsData, decisionsData] = await Promise.all([
        api.dashboard.status(),
        api.dashboard.progress(),
        api.dashboard.logs(50),
        api.dashboard.decisions(50),
      ]);

      setStatus(statusData);
      setProgress(progressData);
      setLogs(logsData);
      setDecisions(decisionsData);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch dashboard data';
      setError(message);
      console.error('Dashboard fetch error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();

    if (autoRefreshMs > 0) {
      const interval = setInterval(refresh, autoRefreshMs);
      return () => clearInterval(interval);
    }
  }, [refresh, autoRefreshMs]);

  return {
    status,
    progress,
    logs,
    decisions,
    isLoading,
    error,
    refresh,
  };
}
