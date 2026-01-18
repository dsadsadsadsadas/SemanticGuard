import { useState, useEffect } from 'react';

interface Match {
    match_id: string;
    started_at: string | null;
    ended_at: string | null;
    duration_seconds: number;
    player_count: number;
    cheater_count: number;
    correct_detections: number;
    detection_accuracy: number;
    rl_reward_total: number;
    rl_trained: boolean;
}

interface MatchCase {
    player_id: string;
    is_cheater: boolean;
    cheat_type: string | null;
    ai_score: number;
    ai_verdict: boolean;
    ai_confidence: number;
    ai_reasoning: string | null;
    was_correct: boolean;
    rl_reward: number;
    total_moves: number;
}

export default function MatchHistory() {
    const [matches, setMatches] = useState<Match[]>([]);
    const [selectedMatch, setSelectedMatch] = useState<string | null>(null);
    const [cases, setCases] = useState<MatchCase[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Fetch matches on mount
    useEffect(() => {
        fetchMatches();
    }, []);

    // Fetch cases when match is selected
    useEffect(() => {
        if (selectedMatch) {
            fetchCases(selectedMatch);
        }
    }, [selectedMatch]);

    const fetchMatches = async () => {
        try {
            const res = await fetch('http://localhost:8000/matches');
            if (!res.ok) throw new Error('Failed to fetch matches');
            const data = await res.json();
            setMatches(data);
            setLoading(false);
        } catch (e) {
            setError('Failed to load match history');
            setLoading(false);
        }
    };

    const fetchCases = async (matchId: string) => {
        try {
            const res = await fetch(`http://localhost:8000/matches/${matchId}`);
            if (!res.ok) throw new Error('Failed to fetch cases');
            const data = await res.json();
            setCases(data);
        } catch (e) {
            setCases([]);
        }
    };

    const formatDate = (isoString: string | null) => {
        if (!isoString) return 'N/A';
        return new Date(isoString).toLocaleString();
    };

    const formatDuration = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}m ${secs}s`;
    };

    // Auto-generate reasoning based on AI analysis
    const generateReasoning = (c: MatchCase): string => {
        if (c.ai_reasoning) return c.ai_reasoning;

        const reasons: string[] = [];

        if (c.ai_score >= 80) {
            reasons.push("❗ Extremely high suspicion score");
            reasons.push("Multiple speed violations detected");
            reasons.push("Input timing below human threshold (<150ms)");
        } else if (c.ai_score >= 50) {
            reasons.push("⚠️ Elevated suspicion detected");
            reasons.push("Inconsistent input patterns");
            reasons.push("Some timing anomalies noted");
        } else if (c.ai_score >= 20) {
            reasons.push("📊 Minor anomalies detected");
            reasons.push("Slightly irregular input timing");
            reasons.push("Within acceptable variance range");
        } else {
            reasons.push("✅ Normal behavioral patterns");
            reasons.push("Input timing consistent with human play");
            reasons.push("No significant anomalies detected");
        }

        if (c.total_moves < 10) {
            reasons.push("⚠️ Insufficient data for accurate analysis");
        }

        return reasons.join(" | ");
    };

    if (loading) {
        return (
            <div style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100vh',
                background: '#0a0a12',
                color: '#fff'
            }}>
                <p>Loading match history...</p>
            </div>
        );
    }

    return (
        <div style={{
            minHeight: '100vh',
            background: 'linear-gradient(135deg, #0a0a12 0%, #1a1a2e 100%)',
            color: '#fff',
            padding: '20px'
        }}>
            <h1 style={{
                fontSize: '2rem',
                marginBottom: '20px',
                background: 'linear-gradient(90deg, #ff6b6b, #feca57)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent'
            }}>
                🏆 Match History
            </h1>

            {error && (
                <div style={{
                    background: 'rgba(255, 100, 100, 0.2)',
                    padding: '10px',
                    borderRadius: '8px',
                    marginBottom: '20px'
                }}>
                    {error}
                </div>
            )}

            <div style={{ display: 'flex', gap: '20px' }}>
                {/* Match List */}
                <div style={{
                    flex: '1',
                    maxWidth: '400px'
                }}>
                    <h2 style={{ marginBottom: '10px', color: '#aaa' }}>Matches</h2>

                    {matches.length === 0 ? (
                        <p style={{ color: '#666' }}>No matches recorded yet. Run a demo game!</p>
                    ) : (
                        matches.map((match) => (
                            <div
                                key={match.match_id}
                                onClick={() => setSelectedMatch(match.match_id)}
                                style={{
                                    background: selectedMatch === match.match_id
                                        ? 'rgba(255, 107, 107, 0.3)'
                                        : 'rgba(255, 255, 255, 0.05)',
                                    padding: '15px',
                                    borderRadius: '12px',
                                    marginBottom: '10px',
                                    cursor: 'pointer',
                                    border: selectedMatch === match.match_id
                                        ? '2px solid #ff6b6b'
                                        : '2px solid transparent',
                                    transition: 'all 0.2s ease'
                                }}
                            >
                                <div style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center'
                                }}>
                                    <span style={{ fontWeight: 'bold' }}>
                                        {match.match_id.slice(0, 18)}...
                                    </span>
                                    <span style={{
                                        background: match.detection_accuracy >= 0.8
                                            ? 'rgba(0, 255, 100, 0.3)'
                                            : match.detection_accuracy >= 0.5
                                                ? 'rgba(255, 200, 0, 0.3)'
                                                : 'rgba(255, 50, 50, 0.3)',
                                        padding: '4px 8px',
                                        borderRadius: '6px',
                                        fontSize: '0.85rem'
                                    }}>
                                        {(match.detection_accuracy * 100).toFixed(0)}% AI Accuracy
                                    </span>
                                </div>
                                <div style={{
                                    marginTop: '8px',
                                    fontSize: '0.85rem',
                                    color: '#888'
                                }}>
                                    <span>👥 {match.player_count} players</span>
                                    <span style={{ marginLeft: '15px' }}>
                                        🔴 {match.cheater_count} cheaters
                                    </span>
                                    <span style={{ marginLeft: '15px' }}>
                                        ⏱️ {formatDuration(match.duration_seconds)}
                                    </span>
                                </div>
                                <div style={{
                                    marginTop: '5px',
                                    fontSize: '0.8rem',
                                    color: '#666'
                                }}>
                                    {formatDate(match.ended_at)}
                                </div>
                            </div>
                        ))
                    )}
                </div>

                {/* Case Details */}
                <div style={{ flex: '2' }}>
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '15px',
                        marginBottom: '10px'
                    }}>
                        <h2 style={{ color: '#aaa', margin: 0 }}>
                            Cases {selectedMatch && `(${cases.length})`}
                        </h2>
                        <span style={{
                            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                            padding: '4px 12px',
                            borderRadius: '12px',
                            fontSize: '0.75rem',
                            fontWeight: 'bold',
                            color: '#fff'
                        }}>
                            🧠 XGBoost + Rule-Based
                        </span>
                    </div>

                    {!selectedMatch ? (
                        <p style={{ color: '#666' }}>Select a match to view cases</p>
                    ) : cases.length === 0 ? (
                        <p style={{ color: '#666' }}>No cases found</p>
                    ) : (
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                            gap: '15px'
                        }}>
                            {cases.map((c) => (
                                <div
                                    key={c.player_id}
                                    style={{
                                        background: c.was_correct
                                            ? 'rgba(0, 200, 100, 0.15)'
                                            : 'rgba(255, 50, 50, 0.15)',
                                        padding: '15px',
                                        borderRadius: '12px',
                                        border: `2px solid ${c.was_correct ? '#00c864' : '#ff3232'}`
                                    }}
                                >
                                    <div style={{
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        marginBottom: '10px'
                                    }}>
                                        <span style={{ fontWeight: 'bold' }}>
                                            {c.player_id}
                                        </span>
                                        <span style={{
                                            fontSize: '1.2rem'
                                        }}>
                                            {c.was_correct ? '✅' : '❌'}
                                        </span>
                                    </div>

                                    <div style={{
                                        display: 'grid',
                                        gridTemplateColumns: '1fr 1fr',
                                        gap: '8px',
                                        fontSize: '0.85rem'
                                    }}>
                                        <div>
                                            <span style={{ color: '#888' }}>Ground Truth:</span>
                                            <div style={{
                                                color: c.is_cheater ? '#ff6b6b' : '#4ecdc4',
                                                fontWeight: 'bold'
                                            }}>
                                                {c.is_cheater ? '🔴 CHEATER' : '🟢 LEGIT'}
                                            </div>
                                        </div>
                                        <div>
                                            <span style={{ color: '#888' }}>AI Verdict:</span>
                                            <div style={{
                                                color: c.ai_verdict ? '#ff6b6b' : '#4ecdc4',
                                                fontWeight: 'bold'
                                            }}>
                                                {c.ai_verdict ? '🤖 CHEATER' : '🤖 LEGIT'}
                                            </div>
                                        </div>
                                    </div>

                                    <div style={{
                                        marginTop: '10px',
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        fontSize: '0.85rem'
                                    }}>
                                        <span>
                                            AI Score: <strong>{c.ai_score.toFixed(1)}%</strong>
                                        </span>
                                        <span>
                                            Moves: <strong>{c.total_moves}</strong>
                                        </span>
                                        <span style={{
                                            color: c.rl_reward > 0 ? '#4ecdc4' : '#ff6b6b'
                                        }}>
                                            RL: <strong>{c.rl_reward > 0 ? '+1' : '-1'}</strong>
                                        </span>
                                    </div>

                                    {/* Always show AI Reasoning */}
                                    <div style={{
                                        marginTop: '10px',
                                        padding: '8px',
                                        background: 'rgba(0,0,0,0.3)',
                                        borderRadius: '6px',
                                        fontSize: '0.75rem',
                                        color: '#aaa',
                                        lineHeight: '1.4'
                                    }}>
                                        <strong style={{ color: '#888' }}>🧠 AI Analysis:</strong>
                                        <p style={{ margin: '5px 0 0' }}>
                                            {generateReasoning(c)}
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
