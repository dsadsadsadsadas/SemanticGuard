export type CaseStatus = 'pending' | 'in_review' | 'cleared' | 'banned' | 'monitoring' | 'escalated';
export type CasePriority = 'low' | 'medium' | 'high' | 'critical';

export interface Case {
    id: number;
    case_id: string;
    player_id: string;
    session_id?: string;
    created_at: string;
    status: CaseStatus;
    priority: CasePriority;
    tier1_score: number;
    tier2_score: number;
    ai_verdict?: string;
    ai_confidence: number;
    ai_reasoning?: string;
    suspicious_features?: Record<string, any>;
}

export interface PlayerStats {
    player_id: string;
    status: string;
    total_sessions: number;
    total_flags: number;
    trust_score: number;
}
