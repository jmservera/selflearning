import { useState, useEffect } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { TopicResponse, TopicDetail } from '@/lib/types';
import { GraphView } from '@/components/knowledge/GraphView';
import { TopicSummary } from '@/components/knowledge/TopicSummary';
import { GapAnalysis } from '@/components/knowledge/GapAnalysis';
import { EntityDetail } from '@/components/knowledge/EntityDetail';

export default function KnowledgeExplorerPage() {
  const [topics, setTopics] = useState<TopicResponse[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [topicDetail, setTopicDetail] = useState<TopicDetail | null>(null);
  const [graphData, setGraphData] = useState<{ entities: any[]; relationships: any[] }>({
    entities: [],
    relationships: [],
  });
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadTopics();
  }, []);

  useEffect(() => {
    if (selectedTopic) {
      loadTopicData(selectedTopic);
    }
  }, [selectedTopic]);

  const loadTopics = async () => {
    try {
      const data = await api.topics.list();
      setTopics(data);
      if (data.length > 0 && !selectedTopic) {
        setSelectedTopic(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load topics:', err);
      setError('Failed to load topics');
    }
  };

  const loadTopicData = async (topicId: string) => {
    setIsLoading(true);
    setError(null);
    setSelectedEntityId(null);

    try {
      const [detail, graph] = await Promise.all([
        api.topics.get(topicId),
        api.knowledge.getGraph(topicId, 100),
      ]);

      setTopicDetail(detail);
      setGraphData({
        entities: graph.entities || [],
        relationships: graph.relationships || [],
      });
    } catch (err) {
      console.error('Failed to load topic data:', err);
      setError('Failed to load topic data');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsLoading(true);
    setError(null);

    try {
      const results = await api.knowledge.search({
        q: searchQuery,
        topic: selectedTopic || undefined,
        limit: 50,
      });

      if (results.items.length > 0) {
        const entityIds = results.items
          .filter(item => item.doc_type === 'entity')
          .map(item => item.id);

        const entities = graphData.entities.filter(e => 
          e.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          entityIds.includes(e.id)
        );

        if (entities.length > 0) {
          setSelectedEntityId(entities[0].id);
        }
      }
    } catch (err) {
      console.error('Search error:', err);
      setError('Search failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-900">
      {/* Left Panel - Topic Summary & Gap Analysis */}
      <div className="w-80 border-r border-slate-700 overflow-y-auto p-4 space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">Topic</label>
          <select
            value={selectedTopic || ''}
            onChange={(e) => setSelectedTopic(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {topics.map(topic => (
              <option key={topic.id} value={topic.id}>
                {topic.name}
              </option>
            ))}
          </select>
        </div>

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

        {topicDetail && !isLoading && (
          <>
            <TopicSummary topic={topicDetail} />
            <GapAnalysis topic={topicDetail} />
          </>
        )}

        {!selectedTopic && !isLoading && (
          <div className="text-center py-12 text-slate-400">
            <p>Select a topic to explore</p>
          </div>
        )}
      </div>

      {/* Center - Knowledge Graph */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Search Bar */}
        <div className="border-b border-slate-700 bg-slate-800/50 p-4">
          <form onSubmit={handleSearch} className="max-w-2xl mx-auto">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search entities, claims, or relationships..."
                className="w-full bg-slate-700 text-slate-100 placeholder-slate-400 rounded-lg pl-10 pr-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </form>
        </div>

        {/* Graph Visualization */}
        <div className="flex-1 p-4">
          {selectedTopic ? (
            <GraphView
              entities={graphData.entities}
              relationships={graphData.relationships}
              onNodeSelect={setSelectedEntityId}
              selectedNodeId={selectedEntityId || undefined}
            />
          ) : (
            <div className="h-full flex items-center justify-center bg-slate-900 rounded-lg border border-slate-700">
              <div className="text-center">
                <div className="text-6xl mb-4">🔍</div>
                <h2 className="text-2xl font-bold text-slate-100 mb-2">Knowledge Explorer</h2>
                <p className="text-slate-400">
                  Select a topic from the left panel to visualize its knowledge graph
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right Panel - Entity Detail */}
      {selectedEntityId && (
        <div className="w-96 flex-shrink-0">
          <EntityDetail
            entityId={selectedEntityId}
            topic={selectedTopic || undefined}
            onClose={() => setSelectedEntityId(null)}
          />
        </div>
      )}
    </div>
  );
}
