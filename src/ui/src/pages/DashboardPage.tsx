import { useDashboard } from '@/hooks/useDashboard';
import { useTopics } from '@/hooks/useTopics';
import { StatusPanel } from '@/components/dashboard/StatusPanel';
import { ProgressChart } from '@/components/dashboard/ProgressChart';
import { ActivityLog } from '@/components/dashboard/ActivityLog';
import { SteeringControls } from '@/components/dashboard/SteeringControls';
import { Loader2 } from 'lucide-react';

export function DashboardPage() {
  const { status, progress, logs, isLoading, error } = useDashboard(5000);
  const {
    createTopic,
    startLearning,
    pauseTopic,
    resumeTopic,
    updatePriority,
  } = useTopics();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
          <p className="text-slate-400">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="bg-rose-500/10 border border-rose-500 rounded-lg p-6 max-w-md">
          <h2 className="text-lg font-semibold text-rose-400 mb-2">Error</h2>
          <p className="text-slate-300">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <StatusPanel initialStatus={status} />
        </div>

        <div className="lg:col-span-2">
          <ProgressChart
            progress={progress}
            onStartLearning={startLearning}
            onPause={pauseTopic}
            onResume={resumeTopic}
            onUpdatePriority={updatePriority}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SteeringControls onCreateTopic={createTopic} />
        <ActivityLog initialLogs={logs} />
      </div>
    </div>
  );
}
