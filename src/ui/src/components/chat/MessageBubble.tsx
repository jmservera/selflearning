import React, { useState } from 'react';
import { User, Bot, ChevronDown, ChevronUp, Cpu, Zap } from 'lucide-react';
import { ChatResponse } from '@/lib/types';
import { CitationCard } from './CitationCard';
import { ConfidenceBar } from '@/components/knowledge/ConfidenceBar';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  response?: ChatResponse;
}

interface MessageBubbleProps {
  message: Message;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const [citationsExpanded, setCitationsExpanded] = useState(false);
  const isUser = message.role === 'user';

  const formatText = (text: string) => {
    return text.split('\n').map((line, i) => (
      <React.Fragment key={i}>
        {line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').split(/<\/?strong>/).map((part, j) => 
          j % 2 === 1 ? <strong key={j}>{part}</strong> : part
        )}
        {i < text.split('\n').length - 1 && <br />}
      </React.Fragment>
    ));
  };

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'} mb-4 group`}>
      <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
        isUser ? 'bg-blue-600' : 'bg-slate-700'
      }`}>
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Bot className="w-4 h-4 text-emerald-400" />
        )}
      </div>

      <div className={`flex-1 max-w-[75%] ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
        <div className={`rounded-2xl px-4 py-3 ${
          isUser 
            ? 'bg-blue-600 text-white rounded-tr-sm' 
            : 'bg-slate-700 text-slate-100 rounded-tl-sm'
        }`}>
          <div className="text-sm leading-relaxed whitespace-pre-wrap">
            {formatText(message.content)}
          </div>
        </div>

        <div className="flex items-center gap-2 mt-1 px-2 text-xs text-slate-400">
          <span>{message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
        </div>

        {!isUser && message.response && (
          <div className="mt-3 w-full space-y-3">
            <div className="flex items-center gap-4 px-2">
              <div className="flex items-center gap-2">
                <Cpu className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-xs text-slate-400">{message.response.model}</span>
              </div>
              <div className="flex items-center gap-2">
                <Zap className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-xs text-slate-400">{message.response.tokens_used.toLocaleString()} tokens</span>
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-slate-400">Confidence:</span>
                  <div className="w-24">
                    <ConfidenceBar value={message.response.confidence} size="sm" showLabel={false} />
                  </div>
                  <span className="text-xs font-semibold text-slate-300">
                    {Math.round(message.response.confidence * 100)}%
                  </span>
                </div>
              </div>
            </div>

            {message.response.sources && message.response.sources.length > 0 && (
              <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700/50">
                <button
                  onClick={() => setCitationsExpanded(!citationsExpanded)}
                  className="w-full flex items-center justify-between text-sm font-medium text-slate-300 hover:text-slate-100 transition-colors"
                >
                  <span>Sources ({message.response.sources.length})</span>
                  {citationsExpanded ? (
                    <ChevronUp className="w-4 h-4" />
                  ) : (
                    <ChevronDown className="w-4 h-4" />
                  )}
                </button>

                {citationsExpanded && (
                  <div className="mt-3 space-y-2">
                    {message.response.sources.map((citation, idx) => (
                      <CitationCard key={`${citation.entity_id}-${idx}`} citation={citation} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
