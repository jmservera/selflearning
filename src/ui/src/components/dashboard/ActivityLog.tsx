import { useEffect, useRef, useState } from 'react';
import { CheckCircle, XCircle } from 'lucide-react';
import type { ActivityLog as ActivityLogType } from '@/lib/types';
import { useWebSocket } from '@/hooks/useWebSocket';

interface ActivityLogProps {
  initialLogs: ActivityLogType[];
}

const serviceIcons: Record<string, string> = {
  scraper: '🕷️',
  extractor: '🔍',
  knowledge: '🧠',
  reasoner: '💭',
  evaluator: '📊',
  orchestrator: '🎭',
  healer: '🏥',
  api: '🌐',
};

export function ActivityLog({ initialLogs }: ActivityLogProps) {
  const [logs, setLogs] = useState<ActivityLogType[]>(initialLogs);
  const scrollRef = useRef<HTMLDivElement>(null);

  useWebSocket({
    path: '/ws/logs',
    onMessage: (message) => {
      if (message.type === 'log_entry') {
        const newLog = message.data as unknown as ActivityLogType;
        setLogs((prev) => [newLog, ...prev].slice(0, 100));
      }
    },
  });

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [logs]);

  useEffect(() => {
    setLogs(initialLogs);
  }, [initialLogs]);

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <h2 className="text-lg font-semibold mb-4">Activity Log</h2>
      
      <div
        ref={scrollRef}
        className="space-y-2 max-h-[500px] overflow-y-auto scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-900"
      >
        {logs.length === 0 ? (
          <div className="text-center py-8 text-slate-500">No activity yet</div>
        ) : (
          logs.map((log) => (
            <div
              key={log.id}
              className="flex items-start gap-3 p-3 rounded-lg bg-slate-900 border border-slate-700 hover:border-slate-600 transition-colors"
            >
              <div className="flex-shrink-0 text-lg">
                {serviceIcons[log.service] || '⚙️'}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-slate-300">
                    {log.service}
                  </span>
                  <span className="text-xs text-slate-500">·</span>
                  <span className="text-xs text-blue-400">{log.action}</span>
                  {log.topic && (
                    <>
                      <span className="text-xs text-slate-500">·</span>
                      <span className="text-xs text-slate-400">{log.topic}</span>
                    </>
                  )}
                </div>
                <p className="text-sm text-slate-400 break-words">{log.details}</p>
                <div className="text-xs text-slate-600 mt-1">
                  {new Date(log.timestamp).toLocaleString()}
                </div>
              </div>

              <div className="flex-shrink-0">
                {log.success ? (
                  <CheckCircle className="w-4 h-4 text-emerald-500" />
                ) : (
                  <XCircle className="w-4 h-4 text-rose-500" />
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
