import type { LearningProgress } from '@/lib/types';
import { TopicCard } from './TopicCard';

interface ProgressChartProps {
  progress: LearningProgress | null;
  onStartLearning: (topicId: string) => Promise<void>;
  onPause: (topicId: string) => Promise<void>;
  onResume: (topicId: string) => Promise<void>;
  onUpdatePriority: (topicId: string, priority: number) => Promise<void>;
}

export function ProgressChart({
  progress,
  onStartLearning,
  onPause,
  onResume,
  onUpdatePriority,
}: ProgressChartProps) {
  if (!progress) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-slate-700 rounded w-1/4"></div>
          <div className="h-24 bg-slate-700 rounded"></div>
          <div className="h-24 bg-slate-700 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <div className="mb-6">
        <h2 className="text-lg font-semibold mb-2">Learning Progress</h2>
        <div className="flex gap-6 text-sm text-slate-400">
          <div>
            <span className="text-slate-500">Overall Expertise: </span>
            <span className="text-blue-400 font-medium">
              {(progress.overall_expertise * 100).toFixed(1)}%
            </span>
          </div>
          <div>
            <span className="text-slate-500">Entities: </span>
            <span className="text-slate-200 font-medium">
              {progress.total_entities.toLocaleString()}
            </span>
          </div>
          <div>
            <span className="text-slate-500">Claims: </span>
            <span className="text-slate-200 font-medium">
              {progress.total_claims.toLocaleString()}
            </span>
          </div>
          <div>
            <span className="text-slate-500">Learning Rate: </span>
            <span className="text-emerald-400 font-medium">
              {progress.learning_rate.toFixed(1)} entities/hr
            </span>
          </div>
        </div>
      </div>

      {progress.topics.length === 0 ? (
        <div className="text-center py-12 text-slate-500">
          No topics yet. Create a topic to start learning.
        </div>
      ) : (
        <div className="space-y-3">
          {progress.topics.map((topic) => (
            <TopicCard
              key={topic.id}
              topic={topic}
              onStartLearning={onStartLearning}
              onPause={onPause}
              onResume={onResume}
              onUpdatePriority={onUpdatePriority}
            />
          ))}
        </div>
      )}
    </div>
  );
}
