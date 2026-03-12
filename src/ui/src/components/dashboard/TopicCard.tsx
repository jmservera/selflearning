import { useState } from 'react';
import { Play, Pause, Circle, ChevronDown, ChevronUp } from 'lucide-react';
import type { TopicResponse } from '@/lib/types';

interface TopicCardProps {
  topic: TopicResponse;
  onStartLearning: (topicId: string) => Promise<void>;
  onPause: (topicId: string) => Promise<void>;
  onResume: (topicId: string) => Promise<void>;
  onUpdatePriority: (topicId: string, priority: number) => Promise<void>;
}

const statusColors = {
  active: 'bg-emerald-500',
  paused: 'bg-amber-500',
  completed: 'bg-blue-500',
  failed: 'bg-rose-500',
  pending: 'bg-slate-500',
};

const statusLabels = {
  active: 'Active',
  paused: 'Paused',
  completed: 'Completed',
  failed: 'Failed',
  pending: 'Pending',
};

export function TopicCard({
  topic,
  onStartLearning,
  onPause,
  onResume,
  onUpdatePriority,
}: TopicCardProps) {
  const [isUpdating, setIsUpdating] = useState(false);

  const handleAction = async (action: () => Promise<void>) => {
    setIsUpdating(true);
    try {
      await action();
    } catch (error) {
      console.error('Action failed:', error);
    } finally {
      setIsUpdating(false);
    }
  };

  const handlePriorityChange = async (delta: number) => {
    const newPriority = Math.max(1, Math.min(10, topic.priority + delta));
    if (newPriority !== topic.priority) {
      await handleAction(() => onUpdatePriority(topic.id, newPriority));
    }
  };

  const progressPercent = (topic.current_expertise / topic.target_expertise) * 100;

  return (
    <div className="bg-slate-900 rounded-lg border border-slate-700 p-4 hover:border-slate-600 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="font-semibold text-slate-100">{topic.name}</h3>
            <span
              className={`px-2 py-0.5 rounded text-xs font-medium text-white ${
                statusColors[topic.status]
              }`}
            >
              {statusLabels[topic.status]}
            </span>
          </div>

          {topic.description && (
            <p className="text-sm text-slate-400 mb-3">{topic.description}</p>
          )}

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="flex-1 bg-slate-800 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-blue-500 h-full transition-all duration-500"
                  style={{ width: `${Math.min(100, progressPercent)}%` }}
                />
              </div>
              <span className="text-xs text-slate-400 w-12 text-right">
                {progressPercent.toFixed(0)}%
              </span>
            </div>

            <div className="flex gap-4 text-xs text-slate-400">
              <span>
                <span className="text-slate-500">Entities:</span>{' '}
                {topic.entity_count.toLocaleString()}
              </span>
              <span>
                <span className="text-slate-500">Claims:</span>{' '}
                {topic.claim_count.toLocaleString()}
              </span>
              <span>
                <span className="text-slate-500">Priority:</span>{' '}
                {topic.priority}/10
              </span>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          {topic.status === 'pending' && (
            <button
              onClick={() => handleAction(() => onStartLearning(topic.id))}
              disabled={isUpdating}
              className="p-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Start Learning"
            >
              <Play className="w-4 h-4" />
            </button>
          )}
          {topic.status === 'active' && (
            <button
              onClick={() => handleAction(() => onPause(topic.id))}
              disabled={isUpdating}
              className="p-2 rounded-lg bg-amber-500 hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Pause"
            >
              <Pause className="w-4 h-4" />
            </button>
          )}
          {topic.status === 'paused' && (
            <button
              onClick={() => handleAction(() => onResume(topic.id))}
              disabled={isUpdating}
              className="p-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              title="Resume"
            >
              <Play className="w-4 h-4" />
            </button>
          )}

          <div className="flex flex-col gap-1">
            <button
              onClick={() => handlePriorityChange(1)}
              disabled={isUpdating || topic.priority >= 10}
              className="p-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              title="Increase Priority"
            >
              <ChevronUp className="w-3 h-3" />
            </button>
            <button
              onClick={() => handlePriorityChange(-1)}
              disabled={isUpdating || topic.priority <= 1}
              className="p-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              title="Decrease Priority"
            >
              <ChevronDown className="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-slate-800 flex items-center gap-2">
        {[...Array(10)].map((_, i) => (
          <Circle
            key={i}
            className={`w-1.5 h-1.5 ${
              i < topic.priority ? 'fill-blue-500 text-blue-500' : 'text-slate-700'
            }`}
          />
        ))}
      </div>
    </div>
  );
}
