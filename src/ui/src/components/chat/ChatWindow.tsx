import React, { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { MessageBubble } from './MessageBubble';
import { ChatResponse } from '@/lib/types';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  response?: ChatResponse;
}

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ messages, isLoading }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [messages, isLoading]);

  return (
    <div 
      ref={containerRef}
      className="flex-1 overflow-y-auto px-4 py-6 space-y-4 scroll-smooth"
      style={{ 
        scrollbarWidth: 'thin',
        scrollbarColor: 'rgb(51 65 85) rgb(15 23 42)'
      }}
    >
      {messages.length === 0 && !isLoading && (
        <div className="flex flex-col items-center justify-center h-full text-center px-4">
          <div className="bg-slate-800 rounded-full p-6 mb-6">
            <svg 
              className="w-16 h-16 text-blue-500" 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path 
                strokeLinecap="round" 
                strokeLinejoin="round" 
                strokeWidth={1.5} 
                d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" 
              />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-slate-100 mb-2">
            Start a conversation
          </h2>
          <p className="text-slate-400 max-w-md">
            Ask me anything about the topics I've learned. I can provide detailed answers with sources and confidence scores.
          </p>
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl">
            <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-left">
              <p className="text-sm text-slate-300">
                "What are the key concepts in quantum computing?"
              </p>
            </div>
            <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-left">
              <p className="text-sm text-slate-300">
                "Explain the relationship between machine learning and AI"
              </p>
            </div>
          </div>
        </div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {isLoading && (
        <div className="flex gap-3 mb-4">
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center">
            <Loader2 className="w-4 h-4 text-emerald-400 animate-spin" />
          </div>
          <div className="flex-1 max-w-[75%]">
            <div className="bg-slate-700 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-2">
                <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-slate-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  );
};
