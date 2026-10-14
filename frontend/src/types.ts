// 前端 API 类型定义

export interface RouteOption {
  id: string
  summary: string
  mode: string
  steps?: RouteStep[]
  duration_min: number | null
  fare_sgd: number | null
  walk_distance_m: number | null
  transfers: number | null
}

export interface RouteStep {
  type: string
  description: string
  line?: string
  distance_m?: number
  duration_min?: number
}

export interface RouteScore {
  route: RouteOption
  score: number
  score_detail: {
    duration: number
    fare: number
    walking: number
    transfers: number
    weather_risk: number
    traffic: number
  }
  constraint_violations: string[]
  feasible: boolean
}

export interface DataSourceEntry {
  source: string
  status: string
}

export interface DataSources {
  routes?: DataSourceEntry
  weather?: DataSourceEntry
  traffic?: DataSourceEntry
  overall: string
}

export interface ChatResponse {
  session_id: string
  reply: string
  needs_clarification: boolean
  route_scores: RouteScore[]
  selected_route: RouteScore | null
  source: string
  data_sources: DataSources
  errors: string[]
}

export interface SessionSummary {
  session_id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface SessionDetail {
  session_id: string
  title: string
  messages: { role: string; content: string; created_at: string }[]
}

export interface CommuteSummary {
  id: number
  origin: string
  destination: string
  departure_time: string | null
  mode: string
  selected_route_id: string | null
  source: string
  created_at: string
}

export interface CommuteDetail {
  id: number
  origin: string
  destination: string
  departure_time: string | null
  mode: string
  recommendation: string
  source: string
  created_at: string
  route_options: RouteScore[]
}

export interface Preferences {
  default_mode: string
  prefer_fewer_transfers: number
  prefer_less_walking: number
  prefer_lower_cost: number
  prefer_shorter_time: number
  max_walk_m: number
  max_transfers: number
}
