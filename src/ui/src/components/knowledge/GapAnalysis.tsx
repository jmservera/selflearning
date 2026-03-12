import React from 'react';
import { AlertTriangle, CheckCircle2, Target, TrendingUp } from 'lucide-react';
import { TopicDetail } from '@/lib/types';

interface GapAnalysisProps {
  topic: TopicDetail;
}

export const GapAnalysis: React.FC<GapAnalysisProps> = ({ topic }) => {
  const gaps = topic.gap_areas || [];
  const coverage = topic.coverage_areas || [];

  const getSeverity = (gapIndex: number): 'critical' | 'moderate' | 'minor' => {
    if (topic.entity_count === 0) return 'critical';
    if (gaps.length <= 3) return gapIndex === 0 ? 'critical' : 'moderate';
    const ratio = gapIndex / gaps.length;
    if (ratio < 0.3) return 'critical';
    if (ratio < 0.7) return 'moderate';
    return 'minor';
  };

  const getSeverityColor = (severity: 'critical' | 'moderate' | 'minor') => {
    switch (severity) {
      case 'critical': return 'border-rose-600/50 bg-rose-900/30 text-rose-300';
      case 'moderate': return 'border-amber-600/50 bg-amber-900/30 text-amber-300';
      case 'minor': return 'border-blue-600/50 bg-blue-900/30 text-blue-300';
    }
  };

  const getSeverityIcon = (severity: 'critical' | 'moderate' | 'minor') => {
    switch (severity) {
      case 'critical': return <AlertTriangle className="w-4 h-4 text-rose-400" />;
      case 'moderate': return <AlertTriangle className="w-4 h-4 text-amber-400" />;
      case 'minor': return <Target className="w-4 h-4 text-blue-400" />;
    }
  };

  const completeness = coverage.length > 0 
    ? Math.min(100, Math.round((coverage.length / (coverage.length + gaps.length)) * 100))
    : 0;

  const getCompletenessColor = () => {
    if (completeness >= 80) return 'text-emerald-400';
    if (completeness >= 50) return 'text-amber-400';
    return 'text-rose-400';
  };

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-slate-100">Knowledge Gaps</h3>
        <div className="flex items-center gap-2">
          <TrendingUp className={`w-4 h-4 ${getCompletenessColor()}`} />
          <span className={`text-sm font-bold ${getCompletenessColor()}`}>
            {completeness}% Complete
          </span>
        </div>
      </div>

      {/* Completeness Bar */}
      <div className="space-y-2">
        <div className="flex justify-between text-xs text-slate-400">
          <span>{coverage.length} covered</span>
          <span>{gaps.length} gaps</span>
        </div>
        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${
              completeness >= 80 
                ? 'bg-gradient-to-r from-emerald-500 to-emerald-600' 
                : completeness >= 50 
                ? 'bg-gradient-to-r from-amber-500 to-amber-600'
                : 'bg-gradient-to-r from-rose-500 to-rose-600'
            }`}
            style={{ width: `${completeness}%` }}
          />
        </div>
      </div>

      {/* Gap Areas */}
      {gaps.length > 0 ? (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-slate-300">Areas to Learn</h4>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {gaps.map((gap, idx) => {
              const severity = getSeverity(idx);
              return (
                <div
                  key={idx}
                  className={`p-3 border rounded-lg ${getSeverityColor(severity)}`}
                >
                  <div className="flex items-start gap-3">
                    {getSeverityIcon(severity)}
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium">{gap}</div>
                      <div className="text-xs opacity-75 mt-1">
                        {severity === 'critical' && 'High priority - critical knowledge gap'}
                        {severity === 'moderate' && 'Medium priority - important area to cover'}
                        {severity === 'minor' && 'Low priority - nice to have coverage'}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <CheckCircle2 className="w-12 h-12 text-emerald-400 mb-3" />
          <p className="text-sm text-slate-300 font-medium">No significant gaps identified</p>
          <p className="text-xs text-slate-400 mt-1">Coverage appears comprehensive</p>
        </div>
      )}

      {/* Suggestions */}
      {gaps.length > 0 && (
        <div className="pt-3 border-t border-slate-700">
          <h4 className="text-sm font-medium text-slate-300 mb-2">Next Steps</h4>
          <ul className="space-y-2 text-sm text-slate-400">
            {gaps.slice(0, 3).map((gap, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="text-blue-400 mt-0.5">•</span>
                <span>Focus learning on <strong className="text-slate-300">{gap}</strong></span>
              </li>
            ))}
            {gaps.length > 3 && (
              <li className="text-xs text-slate-500 italic">
                ...and {gaps.length - 3} more areas
              </li>
            )}
          </ul>
        </div>
      )}

      {/* Coverage vs Gaps Comparison */}
      {coverage.length > 0 && (
        <div className="pt-3 border-t border-slate-700">
          <h4 className="text-sm font-medium text-slate-300 mb-2">Well-Covered Areas</h4>
          <div className="flex flex-wrap gap-2">
            {coverage.slice(0, 5).map((area, idx) => (
              <span
                key={idx}
                className="px-2 py-1 text-xs bg-emerald-600/20 text-emerald-400 border border-emerald-600/30 rounded flex items-center gap-1"
              >
                <CheckCircle2 className="w-3 h-3" />
                {area}
              </span>
            ))}
            {coverage.length > 5 && (
              <span className="px-2 py-1 text-xs bg-slate-700 text-slate-400 rounded">
                +{coverage.length - 5} more
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
