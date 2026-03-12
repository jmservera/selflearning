export type TopicStatus = "active" | "paused" | "completed" | "failed" | "pending";

export interface TopicCreate {
  name: string;
  description?: string;
  priority?: number;
  target_expertise?: number;
  seed_urls?: string[];
  tags?: string[];
}

export interface TopicResponse {
  id: string;
  name: string;
  description?: string;
  status: TopicStatus;
  priority: number;
  current_expertise: number;
  target_expertise: number;
  entity_count: number;
  claim_count: number;
  created_at: string;
  updated_at: string;
}

export interface TopicDetail extends TopicResponse {
  seed_urls: string[];
  tags: string[];
  coverage_areas: string[];
  avg_confidence: number;
  relationship_count: number;
  source_count: number;
  learning_cycles_completed: number;
  last_learning_cycle: string | null;
  gap_areas: string[];
}

export interface PriorityUpdate {
  priority: number;
}

export interface SearchResultItem {
  id: string;
  doc_type: string;
  name: string;
  statement: string;
  topic: string;
  confidence: number;
  score: number;
  highlights: Record<string, string[]>;
}

export interface SearchResponse {
  items: SearchResultItem[];
  total_count: number;
  facets: Record<string, unknown>;
}

export interface ChatRequest {
  question: string;
  topic?: string | null;
  context?: string | null;
  include_sources?: boolean;
}

export interface Citation {
  entity_id: string;
  name: string;
  source_url: string;
  confidence: number;
  snippet: string;
}

export interface ChatResponse {
  answer: string;
  confidence: number;
  sources: Citation[];
  topic: string | null;
  model: string;
  tokens_used: number;
}

export interface ServiceHealth {
  name: string;
  url: string;
  status: string;
  latency_ms: number;
  last_checked: string;
}

export interface SystemHealth {
  status: string;
  services: ServiceHealth[];
  timestamp: string;
}

export interface DashboardStatus {
  current_activity: string;
  active_topics: number;
  total_entities: number;
  total_claims: number;
  active_learning_cycles: number;
  system_health: string;
  last_activity: string | null;
}

export interface LearningProgress {
  topics: TopicResponse[];
  overall_expertise: number;
  total_entities: number;
  total_claims: number;
  total_sources: number;
  learning_rate: number;
}

export interface ActivityLog {
  id: string;
  timestamp: string;
  service: string;
  action: string;
  details: string;
  topic: string | null;
  success: boolean;
}

export interface DecisionLog {
  id: string;
  timestamp: string;
  decision: string;
  reasoning: string;
  topic: string | null;
  outcome: string | null;
}

export interface WSMessage {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface Entity {
  id: string;
  name: string;
  type: string;
  description: string;
  topic: string;
  confidence: number;
  sources: Array<{ url: string; title?: string }>;
  created_at: string;
  updated_at: string;
  relationships?: Array<{
    id: string;
    target_entity: string;
    target_name: string;
    relation_type: string;
    confidence: number;
  }>;
  claims?: Array<{
    id: string;
    statement: string;
    confidence: number;
    source_url?: string;
  }>;
}

export interface KnowledgeGraph {
  entities: Entity[];
  relationships: Array<{
    source: string;
    target: string;
    type: string;
    confidence: number;
  }>;
  topic: string;
}
