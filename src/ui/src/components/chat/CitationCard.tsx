import React, { useState } from 'react';
import { ExternalLink, ChevronDown, ChevronUp } from 'lucide-react';
import { Citation } from '@/lib/types';
import { ConfidenceBar } from '@/components/knowledge/ConfidenceBar';

interface CitationCardProps {
  citation: Citation;
}

export const CitationCard: React.FC<CitationCardProps> = ({ citation }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const maxSnippetLength = 120;
  const isTruncated = citation.snippet.length > maxSnippetLength;
  const displaySnippet = isExpanded 
    ? citation.snippet 
    : citation.snippet.slice(0, maxSnippetLength) + (isTruncated ? '...' : '');

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 hover:border-slate-600 transition-colors">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-semibold text-slate-100 truncate">
            {citation.name}
          </h4>
          {citation.source_url && (
            <a
              href={citation.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 mt-1 group"
            >
              <span className="truncate">{new URL(citation.source_url).hostname}</span>
              <ExternalLink className="w-3 h-3 flex-shrink-0 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
            </a>
          )}
        </div>
        <div className="w-20 flex-shrink-0">
          <ConfidenceBar value={citation.confidence} size="sm" showLabel={true} />
        </div>
      </div>

      <p className="text-sm text-slate-300 leading-relaxed">
        {displaySnippet}
      </p>

      {isTruncated && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="mt-2 text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors"
        >
          {isExpanded ? (
            <>
              Show less <ChevronUp className="w-3 h-3" />
            </>
          ) : (
            <>
              Show more <ChevronDown className="w-3 h-3" />
            </>
          )}
        </button>
      )}
    </div>
  );
};
