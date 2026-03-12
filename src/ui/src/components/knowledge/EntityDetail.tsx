import { useEffect, useState } from 'react';
import { X, ExternalLink, Link2, FileText, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { ConfidenceBar } from './ConfidenceBar';
import type { Entity } from '@/lib/types';

interface EntityDetailProps {
  entityId: string;
  topic?: string;
  onClose: () => void;
}

export const EntityDetail: React.FC<EntityDetailProps> = ({ entityId, topic, onClose }) => {
  const [entity, setEntity] = useState<Entity | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadEntity();
  }, [entityId, topic]);

  const loadEntity = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await api.knowledge.getEntity(entityId, topic);
      setEntity(data);
    } catch (err) {
      console.error('Failed to load entity:', err);
      setError('Failed to load entity details');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="h-full flex flex-col bg-slate-900 border-l border-slate-700">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700 bg-slate-800/50">
        <h2 className="text-lg font-semibold text-slate-100">Entity Details</h2>
        <button
          onClick={onClose}
          className="p-1 text-slate-400 hover:text-slate-100 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
          </div>
        )}

        {error && (
          <div className="p-4 bg-rose-900/50 border border-rose-700 rounded-lg text-rose-200 text-sm">
            {error}
          </div>
        )}

        {entity && (
          <>
            {/* Entity Info */}
            <div className="space-y-3">
              <div>
                <h3 className="text-2xl font-bold text-slate-100 mb-1">{entity.name}</h3>
                <span className="inline-block px-2 py-1 text-xs font-medium bg-blue-600/20 text-blue-400 rounded">
                  {entity.type}
                </span>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-400">Confidence</span>
                  <span className="text-sm font-semibold text-slate-300">
                    {Math.round(entity.confidence * 100)}%
                  </span>
                </div>
                <ConfidenceBar value={entity.confidence} size="md" showLabel={false} />
              </div>

              {entity.description && (
                <p className="text-sm text-slate-300 leading-relaxed">{entity.description}</p>
              )}

              <div className="text-xs text-slate-500">
                Topic: {entity.topic}
              </div>
            </div>

            {/* Sources */}
            {entity.sources && entity.sources.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                  <ExternalLink className="w-4 h-4" />
                  Sources ({entity.sources.length})
                </h4>
                <div className="space-y-2">
                  {entity.sources.map((source, idx) => (
                    <a
                      key={idx}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block p-3 bg-slate-800 border border-slate-700 rounded-lg hover:border-blue-500 transition-colors group"
                    >
                      <div className="text-sm text-slate-300 group-hover:text-blue-400 transition-colors truncate">
                        {source.title || new URL(source.url).hostname}
                      </div>
                      <div className="text-xs text-slate-500 truncate mt-1">{source.url}</div>
                    </a>
                  ))}
                </div>
              </div>
            )}

            {/* Relationships */}
            {entity.relationships && entity.relationships.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                  <Link2 className="w-4 h-4" />
                  Relationships ({entity.relationships.length})
                </h4>
                <div className="space-y-2">
                  {entity.relationships.map((rel) => (
                    <div
                      key={rel.id}
                      className="p-3 bg-slate-800 border border-slate-700 rounded-lg"
                    >
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium text-slate-300">{rel.target_name}</div>
                          <div className="text-xs text-slate-500 mt-1">{rel.relation_type}</div>
                        </div>
                        <div className="w-16 flex-shrink-0">
                          <ConfidenceBar value={rel.confidence} size="sm" showLabel={false} />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Claims */}
            {entity.claims && entity.claims.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                  <FileText className="w-4 h-4" />
                  Claims ({entity.claims.length})
                </h4>
                <div className="space-y-2">
                  {entity.claims.map((claim) => (
                    <div
                      key={claim.id}
                      className="p-3 bg-slate-800 border border-slate-700 rounded-lg"
                    >
                      <p className="text-sm text-slate-300 leading-relaxed mb-2">
                        {claim.statement}
                      </p>
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex-1">
                          <ConfidenceBar value={claim.confidence} size="sm" showLabel={true} />
                        </div>
                        {claim.source_url && (
                          <a
                            href={claim.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-blue-400 hover:text-blue-300"
                          >
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
