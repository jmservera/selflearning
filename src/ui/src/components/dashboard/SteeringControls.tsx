import { useState } from 'react';
import { Plus, Loader2 } from 'lucide-react';
import type { TopicCreate, TopicResponse } from '@/lib/types';

interface SteeringControlsProps {
  onCreateTopic: (data: TopicCreate) => Promise<TopicResponse>;
}

export function SteeringControls({ onCreateTopic }: SteeringControlsProps) {
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formData, setFormData] = useState<TopicCreate>({
    name: '',
    description: '',
    priority: 5,
    target_expertise: 0.8,
    seed_urls: [],
    tags: [],
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      await onCreateTopic({
        ...formData,
        seed_urls: formData.seed_urls?.filter((url) => url.trim() !== '') || [],
        tags: formData.tags?.filter((tag) => tag.trim() !== '') || [],
      });
      
      setFormData({
        name: '',
        description: '',
        priority: 5,
        target_expertise: 0.8,
        seed_urls: [],
        tags: [],
      });
      setIsFormOpen(false);
    } catch (error) {
      console.error('Failed to create topic:', error);
      alert('Failed to create topic. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Steering Controls</h2>
        <button
          onClick={() => setIsFormOpen(!isFormOpen)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>New Topic</span>
        </button>
      </div>

      {isFormOpen && (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Topic Name *
            </label>
            <input
              type="text"
              required
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-slate-100"
              placeholder="e.g., Quantum Computing"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) =>
                setFormData({ ...formData, description: e.target.value })
              }
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-slate-100 h-20"
              placeholder="Brief description of what to learn..."
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Priority: {formData.priority}
              </label>
              <input
                type="range"
                min="1"
                max="10"
                value={formData.priority}
                onChange={(e) =>
                  setFormData({ ...formData, priority: parseInt(e.target.value) })
                }
                className="w-full"
              />
              <div className="flex justify-between text-xs text-slate-500 mt-1">
                <span>Low</span>
                <span>High</span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Target Expertise: {((formData.target_expertise || 0.8) * 100).toFixed(0)}%
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={formData.target_expertise}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    target_expertise: parseFloat(e.target.value),
                  })
                }
                className="w-full"
              />
              <div className="flex justify-between text-xs text-slate-500 mt-1">
                <span>Basic</span>
                <span>Expert</span>
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Seed URLs (one per line)
            </label>
            <textarea
              value={formData.seed_urls?.join('\n') || ''}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  seed_urls: e.target.value.split('\n'),
                })
              }
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-slate-100 h-24 font-mono text-sm"
              placeholder="https://example.com/article1&#10;https://example.com/article2"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Tags (comma-separated)
            </label>
            <input
              type="text"
              value={formData.tags?.join(', ') || ''}
              onChange={(e) =>
                setFormData({
                  ...formData,
                  tags: e.target.value.split(',').map((t) => t.trim()),
                })
              }
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-slate-100"
              placeholder="physics, technology, research"
            />
          </div>

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={isSubmitting || !formData.name}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Creating...</span>
                </>
              ) : (
                <span>Create Topic</span>
              )}
            </button>
            <button
              type="button"
              onClick={() => setIsFormOpen(false)}
              disabled={isSubmitting}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {!isFormOpen && (
        <div className="text-center py-8 text-slate-500">
          Create a new topic to start learning
        </div>
      )}
    </div>
  );
}
