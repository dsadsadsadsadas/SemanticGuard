import { useState, useEffect } from 'react';
import { Search, Filter, ArrowUpRight, ShieldAlert, RefreshCw } from 'lucide-react';
import type { Case } from '../types';

export function CaseList({ onSelectCase }: { onSelectCase: (c: Case) => void }) {
    const [cases, setCases] = useState<Case[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchCases = async () => {
        setLoading(true);
        try {
            const response = await fetch('http://localhost:8000/api/cases');
            if (!response.ok) throw new Error('Failed to fetch cases');
            const data = await response.json();
            setCases(data);
            setError(null);
        } catch (e) {
            setError('Could not load cases. Is the server running?');
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchCases();
        // Poll every 5 seconds for new cases
        const interval = setInterval(fetchCases, 5000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="flex flex-col h-full bg-background">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-border">
                <div>
                    <h2 className="text-xl font-bold tracking-tight">Active Cases</h2>
                    <p className="text-sm text-muted-foreground mt-1">
                        {loading ? 'Loading...' : `${cases.length} cases found`}
                    </p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={fetchCases}
                        className="inline-flex items-center justify-center rounded-md border border-input bg-background h-10 w-10 hover:bg-accent hover:text-accent-foreground"
                    >
                        <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <input
                            type="text"
                            placeholder="Search case ID or player..."
                            className="h-10 rounded-md border border-input bg-background pl-9 pr-4 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                    </div>
                    <button className="inline-flex items-center justify-center rounded-md border border-input bg-background h-10 w-10 hover:bg-accent hover:text-accent-foreground">
                        <Filter className="h-4 w-4" />
                    </button>
                </div>
            </div>

            {/* Error State */}
            {error && (
                <div className="p-6">
                    <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-destructive">
                        {error}
                    </div>
                </div>
            )}

            {/* Empty State */}
            {!loading && !error && cases.length === 0 && (
                <div className="flex-1 flex items-center justify-center">
                    <div className="text-center text-muted-foreground">
                        <ShieldAlert className="h-12 w-12 mx-auto mb-4 opacity-50" />
                        <p className="font-medium">No cases yet</p>
                        <p className="text-sm mt-1">Run the demo to generate some cheater cases!</p>
                        <code className="mt-4 block text-xs bg-secondary p-2 rounded">python run_demo.py</code>
                    </div>
                </div>
            )}

            {/* List */}
            <div className="flex-1 overflow-auto p-6 space-y-4">
                {cases.map((c) => (
                    <div
                        key={c.id || c.case_id}
                        onClick={() => onSelectCase(c)}
                        className="group relative flex items-center justify-between rounded-lg border border-border bg-card p-4 transition-all hover:border-primary/50 hover:bg-secondary/40 cursor-pointer"
                    >
                        <div className="flex items-center gap-4">
                            {/* Status Icon */}
                            <div className={`flex h-10 w-10 items-center justify-center rounded-full border ${c.priority === 'high' || c.priority === 'critical'
                                    ? 'bg-destructive/10 border-destructive text-destructive'
                                    : c.priority === 'medium'
                                        ? 'bg-yellow-500/10 border-yellow-500 text-yellow-500'
                                        : 'bg-blue-500/10 border-blue-500 text-blue-500'
                                }`}>
                                <ShieldAlert className="h-5 w-5" />
                            </div>

                            <div>
                                <div className="flex items-center gap-2">
                                    <span className="font-semibold">{c.player_id}</span>
                                    <span className="text-xs text-muted-foreground font-mono">{c.case_id}</span>
                                </div>
                                <div className="flex items-center gap-2 mt-1">
                                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${c.status === 'pending' ? 'bg-yellow-500/10 text-yellow-500' :
                                            c.status === 'cleared' ? 'bg-green-500/10 text-green-500' :
                                                c.status === 'banned' ? 'bg-destructive/10 text-destructive' :
                                                    'bg-secondary text-secondary-foreground'
                                        }`}>
                                        {c.status}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                        • {c.priority} priority
                                    </span>
                                </div>
                            </div>
                        </div>

                        {/* Scores */}
                        <div className="flex items-center gap-8">
                            <div className="text-right">
                                <p className="text-xs text-muted-foreground">Tier 1 Score</p>
                                <p className={`text-lg font-bold ${c.tier1_score > 0.8 ? 'text-destructive' :
                                        c.tier1_score > 0.5 ? 'text-yellow-500' :
                                            'text-muted-foreground'
                                    }`}>
                                    {(c.tier1_score * 100).toFixed(0)}%
                                </p>
                            </div>
                            <ArrowUpRight className="h-5 w-5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
