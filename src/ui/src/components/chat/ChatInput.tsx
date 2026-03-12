import React, { useState, useRef, useEffect } from 'react';
import { Send, Trash2, Filter } from 'lucide-react';
import { TopicResponse } from '@/lib/types';

interface ChatInputProps {
  onSendMessage: (message: string, topic?: string) => void;
  onClearConversation: () => void;
  isLoading: boolean;
  topics: TopicResponse[];
  selectedTopic?: string;
  onTopicChange: (topicId?: string) => void;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  onClearConversation,
  isLoading,
  topics,
  selectedTopic,
  onTopicChange,
}) => {
  const [message, setMessage] = useState('');
  const [showTopicFilter, setShowTopicFilter] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 112) + 'px';
    }
  }, [message]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim() && !isLoading) {
      onSendMessage(message.trim(), selectedTopic);
      setMessage('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const selectedTopicName = selectedTopic 
    ? topics.find(t => t.id === selectedTopic)?.name 
    : undefined;

  return (
    <div className="border-t border-slate-700 bg-slate-800/50 backdrop-blur-sm">
      <div className="max-w-4xl mx-auto p-4">
        <div className="flex items-center gap-2 mb-2">
          <div className="relative flex-1">
            <button
              onClick={() => setShowTopicFilter(!showTopicFilter)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                selectedTopic
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              <Filter className="w-3.5 h-3.5" />
              {selectedTopicName || 'All Topics'}
            </button>

            {showTopicFilter && (
              <div className="absolute bottom-full mb-2 left-0 w-64 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-10 max-h-64 overflow-y-auto">
                <button
                  onClick={() => {
                    onTopicChange(undefined);
                    setShowTopicFilter(false);
                  }}
                  className={`w-full text-left px-4 py-2 hover:bg-slate-700 transition-colors text-sm ${
                    !selectedTopic ? 'bg-slate-700 text-white' : 'text-slate-300'
                  }`}
                >
                  All Topics
                </button>
                {topics.map(topic => (
                  <button
                    key={topic.id}
                    onClick={() => {
                      onTopicChange(topic.id);
                      setShowTopicFilter(false);
                    }}
                    className={`w-full text-left px-4 py-2 hover:bg-slate-700 transition-colors text-sm ${
                      selectedTopic === topic.id ? 'bg-slate-700 text-white' : 'text-slate-300'
                    }`}
                  >
                    {topic.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={onClearConversation}
            className="p-2 rounded-lg bg-slate-700 text-slate-300 hover:bg-rose-600 hover:text-white transition-colors"
            title="Clear conversation"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex gap-2">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question..."
            disabled={isLoading}
            className="flex-1 bg-slate-700 text-slate-100 placeholder-slate-400 rounded-lg px-4 py-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            rows={1}
            style={{ minHeight: '48px', maxHeight: '112px' }}
          />
          <button
            type="submit"
            disabled={!message.trim() || isLoading}
            className="px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2 font-medium"
          >
            <Send className="w-4 h-4" />
            Send
          </button>
        </form>

        <p className="text-xs text-slate-500 mt-2 text-center">
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  );
};
