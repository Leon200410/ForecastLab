// Mirrors backend pydantic models (PRD §8). Backend is the source of truth.
export type Side = 'YES' | 'NO'
export type Confidence = 'low' | 'med' | 'high'
export type Status = 'open' | 'resolved' | 'void'

export interface Market {
  id: string
  question: string
  description?: string | null
  category?: string | null
  opened_at?: string | null
  close_at?: string | null
  status: Status
  current_prob?: number | null
  resolution?: 0 | 1 | null
  resolved_at?: string | null
  url?: string | null
}

export interface Evidence {
  market_id: string
  url: string
  title: string
  summary: string
  relevance: number
}

export interface ForecastRun {
  probability: number
  confidence: Confidence
  rationale: string
  key_factors: string[]
}

export interface Bet {
  id: string
  market_id: string
  forecast_id: string
  side: Side
  stake: number
  entry_prob: number
  shares: number
  note?: string | null
  created_at: string
  status: 'pending' | 'resolved'
  current_price?: number | null
  unrealized_pnl?: number | null
  outcome?: 0 | 1 | null
  pnl?: number | null
}

export interface Forecast {
  id: string
  market_id: string
  agent_prob: number
  agent_prob_calibrated?: number | null
  market_prob_at_analysis: number
  confidence: Confidence
  rationale: string
  key_factors: string[]
  runs: ForecastRun[]
  prompt_version?: string
  retrieved_lessons: string[]
  evidence: Evidence[]
  created_at: string
  status: 'pending' | 'resolved'
  outcome?: 0 | 1 | null
  brier?: number | null
  market_brier?: number | null
  reviewed: boolean
  question?: string | null   // detail endpoint joins these from the market
  url?: string | null
  opened_at?: string | null
  close_at?: string | null
  bet?: Bet | null
  review?: Review | null
}

export interface Review {
  forecast_id: string
  market_id: string
  question: string
  agent_prob: number
  outcome: 0 | 1
  agent_brier: number
  market_brier: number
  bet_pnl?: number | null
  what_happened: string
  why: string
  lesson: string
  created_at: string
}

export interface Position {
  id: string
  market_id: string
  question?: string | null
  url?: string | null
  opened_at?: string | null
  close_at?: string | null
  category?: string | null
  created_at: string
  agent_prob: number
  market_prob_at_analysis: number
  confidence: Confidence
  status: 'pending' | 'resolved'
  outcome?: 0 | 1 | null
  brier?: number | null
  market_brier?: number | null
  reviewed: boolean
  market_status?: Status | null
  market_current_prob?: number | null
  bet?: Bet | null
}

export interface AccountSummary {
  starting_balance: number
  cash_balance: number
  open_positions_value: number
  equity: number
  realized_pnl: number
  unrealized_pnl: number
  return_pct: number
  open_count: number
}

export interface Holding {
  id: string
  market_id: string
  forecast_id: string
  question?: string | null
  url?: string | null
  opened_at?: string | null
  close_at?: string | null
  side: Side
  stake: number
  entry_prob: number
  shares: number
  current_price?: number | null
  unrealized_pnl?: number | null
  created_at: string
}

export interface CalibrationBucket {
  bucket: number
  lo: number
  hi: number
  mean_pred: number
  freq: number
  count: number
}

export interface OutcomeRef {
  market_id: string
  name: string
  prob?: number | null
  url?: string | null
}

export interface EventGroup {
  kind: 'event'
  event_id: string
  event_title: string
  url?: string | null
  category?: string | null
  outcomes: OutcomeRef[]
}

export type GroupedItem = { kind: 'single'; market: Market } | EventGroup

export interface AuditEntry {
  t: string
  user: string
  action: string
  target: string
}

export interface EvalSummary {
  forecasts: {
    n: number
    agent_brier?: number
    market_brier?: number
    beats_market?: boolean
    accuracy?: number
    log_loss?: number
    calibration?: CalibrationBucket[]
    agent_brier_calibrated?: number
    n_calibrated?: number
    by_version?: Record<string, { n: number; agent_brier: number; market_brier: number }>
  }
  points?: { a: number; m: number; o: 0 | 1 }[]
  portfolio: AccountSummary
  kb_size: number
  cost: {
    total_usd: number; today_usd?: number; calls: number; max_spend_usd: number
    day?: string; by_kind?: Record<string, number>
  }
  cache?: { hits: number; misses: number; hit_rate: number }
  llm_mode: string
  data_source: string
}
