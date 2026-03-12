import React from 'react';
import { Target, Database, Link2, FileText, Globe, TrendingUp, Calendar } from 'lucide-react';
import { TopicDetail } from '@/lib/types';
import { ConfidenceBar } from './ConfidenceBar';

interface TopicSummaryProps {
  topic: TopicDetail;
}

export const TopicSummary: React.FC<TopicSummaryProps> = ({ topic }) => {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-emerald-600/20 text-emerald-400 border-emerald-600/30';
      case 'paused': return 'bg-amber-600/20 text-amber-400 border-amber-600/30';
      case 'completed': return 'bg-blue-600/20 text-blue-400 border-blue-600/30';
      case 'failed': return 'bg-rose-600/20 text-rose-400 border-rose-600/30';
      default: return 'bg-slate-600/20 text-slate-400 border-slate-600/30';
    }
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const expertiseProgress = topic.target_expertise > 0 
    ? topic.current_expertise / topic.target_expertise 
    : 0;

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-xl font-bold text-slate-100 mb-2 truncate">{topic.name}</h3>
          <p className="text-sm text-slate-300 leading-relaxed">{topic.description}</p>
        </div>
        <span className={`px-3 py-1 text-xs font-medium rounded-full border ${getStatusColor(topic.status)}`}>
          {topic.status}
        </span>
      </div>

      {/* Expertise Progress */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-slate-300 flex items-center gap-2">
            <Target className="w-4 h-4" />
            Expertise Progress
          </span>
          <span className="text-sm text-slate-400">
            {topic.current_expertise} / {topic.target_expertise}
          </span>
        </div>
        <div className="h-2.5 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-500 to-blue-600 transition-all duration-500"
            style={{ width: `${Math.min(expertiseProgress * 100, 100)}%` }}
          />
        </div>
      </div>

      {/* Average Confidence */}
      <div className="space-y-2">
        <span className="text-sm font-medium text-slate-300">Average Confidence</span>
        <ConfidenceBar value={topic.avg_confidence} size="md" showLabel={true} />
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-slate-900/50 rounded-lg p-3">
          <div className="flex items-center gap-2 text-slate-400 mb-1">
            <Database className="w-4 h-4" />
            <span className="text-xs">Entities</span>
          </div>
          <div className="text-2xl font-bold text-slate-100">{topic.entity_count}</div>
        </div>

        <div className="bg-slate-900/50 rounded-lg p-3">
          <div className="flex items-center gap-2 text-slate-400 mb-1">
            <FileText className="w-4 h-4" />
            <span className="text-xs">Claims</span>
          </div>
          <div className="text-2xl font-bold text-slate-100">{topic.claim_count}</div>
        </div>

        <div className="bg-slate-900/50 rounded-lg p-3">
          <div className="flex items-center gap-2 text-slate-400 mb-1">
            <Link2 className="w-4 h-4" />
            <span className="text-xs">Relationships</span>
          </div>
          <div className="text-2xl font-bold text-slate-100">{topic.relationship_count}</div>
        </div>

        <div className="bg-slate-900/50 rounded-lg p-3">
          <div className="flex items-center gap-2 text-slate-400 mb-1">
            <Globe className="w-4 h-4" />
            <span className="text-xs">Sources</span>
          </div>
          <div className="text-2xl font-bold text-slate-100">{topic.source_count}</div>
        </div>
      </div>

      {/* Coverage Areas */}
      {topic.coverage_areas && topic.coverage_areas.length > 0 && (
        <div className="space-y-2">
          <span className="text-sm font-medium text-slate-300">Coverage Areas</span>
          <div className="flex flex-wrap gap-2">
            {topic.coverage_areas.map((area, idx) => (
              <span
                key={idx}
                className="px-2 py-1 text-xs bg-emerald-600/20 text-emerald-400 border border-emerald-600/30 rounded"
              >
                {area}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Learning Info */}
      <div className="pt-3 border-t border-slate-700 space-y-2 text-sm">
        <div className="flex items-center justify-between text-slate-400">
          <span className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4" />
            Learning Cycles
          </span>
          <span className="text-slate-300 font-medium">{topic.learning_cycles_completed}</span>
        </div>
        <div className="flex items-center justify-between text-slate-400">
          <span className="flex items-center gap-2">
            <Calendar className="w-4 h-4" />
            Last Cycle
          </span>
          <span className="text-slate-300">{formatDate(topic.last_learning_cycle)}</span>
        </div>
      </div>
    </div>
  );
};
