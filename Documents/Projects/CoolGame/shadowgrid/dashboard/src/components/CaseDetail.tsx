import { Crosshair, Zap, CheckCircle, XCircle } from 'lucide-react';
import type { Case } from '../types';
import { ReplayViewer } from './ReplayViewer';

export function CaseDetail({ caseData, onClose }: { caseData: Case, onClose: () => void }) {
    if (!caseData) return null;

    return (
        <div className="h-full flex flex-col bg-background">
            {/* Header */}
            <div className="border-b border-border p-6 flex items-center justify-between bg-card/50">
                <div>
                    <div className="flex items-center gap-3">
                        <h2 className="text-2xl font-bold tracking-tight">{caseData.player_id}</h2>
                        <span className="rounded-full bg-destructive/20 px-3 py-1 text-xs font-medium text-destructive">
                            {caseData.priority.toUpperCase()} PRIORITY
                        </span>
                    </div>
                    <p className="text-sm text-muted-foreground mt-1 font-mono">{caseData.case_id} • Session {caseData.session_id}</p>
                </div>
                <div className="flex gap-3">
                    <button
                        onClick={onClose}
                        className="rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-accent"
                    >
                        Close
                    </button>
                    <button className="flex items-center gap-2 rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90">
                        <XCircle className="h-4 w-4" />
                        Ban Player
                    </button>
                    <button className="flex items-center gap-2 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700">
                        <CheckCircle className="h-4 w-4" />
                        Clear
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-auto p-6 grid grid-cols-3 gap-6">
                {/* Left Column: Stats & AI */}
                <div className="col-span-1 space-y-6">
                    {/* AI Verdict Card */}
                    <div className="rounded-lg border border-border bg-card p-5">
                        <h3 className="font-semibold mb-4 flex items-center gap-2">
                            <Zap className="h-4 w-4 text-primary" />
                            AI Analysis
                        </h3>

                        <div className="space-y-4">
                            <div>
                                <div className="flex justify-between text-sm mb-1">
                                    <span className="text-muted-foreground">Confidence Score</span>
                                    <span className="font-medium">{(caseData.ai_confidence * 100).toFixed(0)}%</span>
                                </div>
                                <div className="h-2 rounded-full bg-secondary overflow-hidden">
                                    <div
                                        className="h-full bg-primary transition-all"
                                        style={{ width: `${caseData.ai_confidence * 100}%` }}
                                    />
                                </div>
                            </div>

                            <div className="rounded-md bg-secondary/50 p-3 text-sm">
                                <p className="text-muted-foreground mb-1 text-xs uppercase tracking-wider">Reasoning</p>
                                <p>{caseData.ai_reasoning}</p>
                            </div>
                        </div>
                    </div>

                    {/* Model Scores */}
                    <div className="rounded-lg border border-border bg-card p-5">
                        <h3 className="font-semibold mb-4 flex items-center gap-2">
                            <Crosshair className="h-4 w-4 text-primary" />
                            Model Scores
                        </h3>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="rounded-md bg-background p-3 border border-border text-center">
                                <p className="text-xs text-muted-foreground uppercase">Tier 1 (XGB)</p>
                                <p className="text-xl font-bold mt-1 text-primary">{(caseData.tier1_score * 100).toFixed(0)}</p>
                            </div>
                            <div className="rounded-md bg-background p-3 border border-border text-center">
                                <p className="text-xs text-muted-foreground uppercase">Tier 2 (TabNet)</p>
                                <p className="text-xl font-bold mt-1 text-yellow-500">{(caseData.tier2_score * 100).toFixed(0)}</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Right Column: Evidence / Replay */}
                <div className="col-span-2 space-y-6">
                    {/* Replay Viewer */}
                    <ReplayViewer sessionId={caseData.session_id} />

                    {/* Feature Data */}
                    <div className="rounded-lg border border-border bg-card p-5">
                        <h3 className="font-semibold mb-4">Suspicious Features</h3>
                        <div className="grid grid-cols-3 gap-4">
                            <FeatureCard label="Avg Speed" value="14.2 m/s" anomaly />
                            <FeatureCard label="Reaction Time" value="32ms" anomaly />
                            <FeatureCard label="Wall Collisions" value="0" />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function FeatureCard({ label, value, anomaly }: any) {
    return (
        <div className={`p-3 rounded border ${anomaly ? 'border-destructive/50 bg-destructive/5' : 'border-border bg-background'}`}>
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={`font-mono font-bold ${anomaly ? 'text-destructive' : 'text-foreground'}`}>{value}</p>
        </div>
    )
}
