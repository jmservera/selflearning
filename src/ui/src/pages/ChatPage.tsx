import { useState, useEffect } from 'react';
import { Menu, X } from 'lucide-react';
import { ChatWindow } from '@/components/chat/ChatWindow';
import { ChatInput } from '@/components/chat/ChatInput';
import { api } from '@/lib/api';
import { TopicResponse, ChatResponse } from '@/lib/types';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  response?: ChatResponse;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [topics, setTopics] = useState<TopicResponse[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<string | undefined>();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadTopics();
  }, []);

  const loadTopics = async () => {
    try {
      const topicsData = await api.topics.list();
      setTopics(topicsData);
    } catch (err) {
      console.error('Failed to load topics:', err);
      setError('Failed to load topics');
    }
  };

  const handleSendMessage = async (content: string, topic?: string) => {
    const userMessage: Message = {
      id: `msg-${Date.now()}-user`,
      role: 'user',
      content,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    try {
      const response = await api.chat.send({
        question: content,
        topic: topic || null,
        include_sources: true,
      });

      const assistantMessage: Message = {
        id: `msg-${Date.now()}-assistant`,
        role: 'assistant',
        content: response.answer,
        timestamp: new Date(),
        response,
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      console.error('Chat error:', err);
      setError('Failed to get response. Please try again.');
      
      const errorMessage: Message = {
        id: `msg-${Date.now()}-error`,
        role: 'assistant',
        content: 'I apologize, but I encountered an error processing your request. Please try again.',
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearConversation = () => {
    if (window.confirm('Clear all messages?')) {
      setMessages([]);
      setError(null);
    }
  };

  return (
    <div className="flex h-screen bg-slate-900">
      {/* Sidebar - Topic selector */}
      <div
        className={`fixed lg:relative inset-y-0 left-0 z-30 w-64 bg-slate-800 border-r border-slate-700 transform transition-transform duration-200 ease-in-out ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-slate-100">Topics</h2>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-1 text-slate-400 hover:text-slate-100 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 space-y-2 overflow-y-auto" style={{ height: 'calc(100vh - 73px)' }}>
          <button
            onClick={() => {
              setSelectedTopic(undefined);
              setSidebarOpen(false);
            }}
            className={`w-full text-left px-4 py-3 rounded-lg transition-colors ${
              !selectedTopic
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            <div className="font-medium">All Topics</div>
            <div className="text-xs opacity-75 mt-1">Ask about anything</div>
          </button>

          {topics.length === 0 && (
            <div className="text-sm text-slate-400 text-center py-8">
              No topics available yet
            </div>
          )}

          {topics.map(topic => (
            <button
              key={topic.id}
              onClick={() => {
                setSelectedTopic(topic.id);
                setSidebarOpen(false);
              }}
              className={`w-full text-left px-4 py-3 rounded-lg transition-colors ${
                selectedTopic === topic.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              <div className="font-medium truncate">{topic.name}</div>
              <div className="text-xs opacity-75 mt-1">
                {topic.entity_count} entities • {topic.claim_count} claims
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-20 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-700 bg-slate-800/50 backdrop-blur-sm">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden p-2 text-slate-400 hover:text-slate-100 transition-colors"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold text-slate-100 truncate">
              {selectedTopic 
                ? topics.find(t => t.id === selectedTopic)?.name || 'Chat'
                : 'Chat with Knowledge Base'}
            </h1>
            <p className="text-xs text-slate-400">
              Ask questions and get AI-powered answers with sources
            </p>
          </div>
        </div>

        {error && (
          <div className="mx-4 mt-4 p-3 bg-rose-900/50 border border-rose-700 rounded-lg text-rose-200 text-sm">
            {error}
          </div>
        )}

        {/* Chat messages */}
        <ChatWindow messages={messages} isLoading={isLoading} />

        {/* Input area */}
        <ChatInput
          onSendMessage={handleSendMessage}
          onClearConversation={handleClearConversation}
          isLoading={isLoading}
          topics={topics}
          selectedTopic={selectedTopic}
          onTopicChange={setSelectedTopic}
        />
      </div>
    </div>
  );
}
