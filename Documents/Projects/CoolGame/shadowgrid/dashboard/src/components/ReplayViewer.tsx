import { useState, useEffect, useRef } from 'react';
import { Play, Pause, SkipBack, FastForward, AlertTriangle } from 'lucide-react';

interface ReplayData {
    t: number;  // timestamp
    x: number;
    y: number;
    d?: string; // direction
}

interface ReplayViewerProps {
    sessionId?: string;
    replayData?: ReplayData[];
}

export function ReplayViewer({ sessionId, replayData: providedData }: ReplayViewerProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [playing, setPlaying] = useState(false);
    const [currentFrame, setCurrentFrame] = useState(0);
    const [replayData, setReplayData] = useState<ReplayData[]>(providedData || []);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const GRID_SIZE = 20;
    const CELL_SIZE = 20;

    // Generate demo replay data if none provided
    useEffect(() => {
        if (!providedData && sessionId) {
            // Fetch from API
            setLoading(true);
            fetch(`http://localhost:8000/api/sessions/${sessionId}/replay`)
                .then(res => res.json())
                .then(data => {
                    if (data.replay_data) {
                        setReplayData(data.replay_data);
                    } else {
                        // Generate demo data
                        generateDemoReplay();
                    }
                })
                .catch(() => {
                    generateDemoReplay();
                })
                .finally(() => setLoading(false));
        } else if (!providedData) {
            generateDemoReplay();
        }
    }, [sessionId]);

    const generateDemoReplay = () => {
        // Generate a demo replay showing suspicious behavior
        const demo: ReplayData[] = [];
        let x = 5, y = 5;

        for (let i = 0; i < 100; i++) {
            // Normal movement with occasional "speed bursts"
            const isSuspicious = i > 30 && i < 50;

            if (isSuspicious && i % 2 === 0) {
                // Speed hack: move 2 tiles at once
                x = Math.min(GRID_SIZE - 1, Math.max(0, x + (Math.random() > 0.5 ? 2 : -2)));
                y = Math.min(GRID_SIZE - 1, Math.max(0, y + (Math.random() > 0.5 ? 2 : -2)));
            } else {
                // Normal movement
                const dir = Math.floor(Math.random() * 4);
                if (dir === 0 && y > 0) y--;
                if (dir === 1 && y < GRID_SIZE - 1) y++;
                if (dir === 2 && x > 0) x--;
                if (dir === 3 && x < GRID_SIZE - 1) x++;
            }

            demo.push({ t: i * (isSuspicious ? 50 : 200), x, y });
        }

        setReplayData(demo);
    };

    // Animation loop
    useEffect(() => {
        if (!playing || replayData.length === 0) return;

        const interval = setInterval(() => {
            setCurrentFrame(prev => {
                if (prev >= replayData.length - 1) {
                    setPlaying(false);
                    return prev;
                }
                return prev + 1;
            });
        }, 100);

        return () => clearInterval(interval);
    }, [playing, replayData.length]);

    // Draw on canvas
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const width = canvas.width;
        const height = canvas.height;
        const cellW = width / GRID_SIZE;
        const cellH = height / GRID_SIZE;

        // Clear
        ctx.fillStyle = '#0a0a0a';
        ctx.fillRect(0, 0, width, height);

        // Draw grid
        ctx.strokeStyle = '#1a1a2e';
        ctx.lineWidth = 1;
        for (let i = 0; i <= GRID_SIZE; i++) {
            ctx.beginPath();
            ctx.moveTo(i * cellW, 0);
            ctx.lineTo(i * cellW, height);
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(0, i * cellH);
            ctx.lineTo(width, i * cellH);
            ctx.stroke();
        }

        // Draw trail
        if (replayData.length > 0) {
            ctx.strokeStyle = 'rgba(239, 68, 68, 0.3)';
            ctx.lineWidth = 2;
            ctx.beginPath();

            for (let i = 0; i <= currentFrame && i < replayData.length; i++) {
                const pos = replayData[i];
                const px = pos.x * cellW + cellW / 2;
                const py = pos.y * cellH + cellH / 2;

                if (i === 0) {
                    ctx.moveTo(px, py);
                } else {
                    ctx.lineTo(px, py);
                }
            }
            ctx.stroke();

            // Draw current position
            if (currentFrame < replayData.length) {
                const current = replayData[currentFrame];

                // Check if this is a suspicious frame (big jump)
                let isSuspicious = false;
                if (currentFrame > 0) {
                    const prev = replayData[currentFrame - 1];
                    const dist = Math.abs(current.x - prev.x) + Math.abs(current.y - prev.y);
                    isSuspicious = dist > 1;
                }

                // Glow effect
                const gradient = ctx.createRadialGradient(
                    current.x * cellW + cellW / 2,
                    current.y * cellH + cellH / 2,
                    0,
                    current.x * cellW + cellW / 2,
                    current.y * cellH + cellH / 2,
                    cellW
                );
                gradient.addColorStop(0, isSuspicious ? 'rgba(239, 68, 68, 0.8)' : 'rgba(34, 197, 94, 0.8)');
                gradient.addColorStop(1, 'transparent');
                ctx.fillStyle = gradient;
                ctx.fillRect(
                    current.x * cellW - cellW / 2,
                    current.y * cellH - cellH / 2,
                    cellW * 2,
                    cellH * 2
                );

                // Player dot
                ctx.beginPath();
                ctx.fillStyle = isSuspicious ? '#ef4444' : '#22c55e';
                ctx.arc(
                    current.x * cellW + cellW / 2,
                    current.y * cellH + cellH / 2,
                    cellW / 3,
                    0,
                    Math.PI * 2
                );
                ctx.fill();

                // Suspicious indicator
                if (isSuspicious) {
                    ctx.fillStyle = '#ef4444';
                    ctx.font = 'bold 12px sans-serif';
                    ctx.fillText('⚠️ SPEED!', current.x * cellW + cellW, current.y * cellH);
                }
            }
        }
    }, [currentFrame, replayData]);

    if (loading) {
        return (
            <div className="aspect-video bg-black rounded-lg flex items-center justify-center">
                <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
            </div>
        );
    }

    return (
        <div className="rounded-lg border border-border bg-black overflow-hidden">
            {/* Canvas */}
            <div className="aspect-video relative">
                <canvas
                    ref={canvasRef}
                    width={400}
                    height={400}
                    className="w-full h-full"
                />

                {/* Overlay info */}
                <div className="absolute top-2 left-2 bg-black/70 px-2 py-1 rounded text-xs font-mono">
                    Frame {currentFrame + 1} / {replayData.length}
                </div>

                {replayData.length > 0 && currentFrame > 0 && (() => {
                    const prev = replayData[Math.max(0, currentFrame - 1)];
                    const curr = replayData[currentFrame];
                    const dist = Math.abs(curr.x - prev.x) + Math.abs(curr.y - prev.y);
                    if (dist > 1) {
                        return (
                            <div className="absolute top-2 right-2 bg-destructive/90 px-2 py-1 rounded text-xs font-bold flex items-center gap-1">
                                <AlertTriangle className="h-3 w-3" />
                                ANOMALY DETECTED
                            </div>
                        );
                    }
                    return null;
                })()}
            </div>

            {/* Controls */}
            <div className="p-3 border-t border-border flex items-center gap-4">
                <button
                    onClick={() => setCurrentFrame(0)}
                    className="p-2 hover:bg-secondary rounded"
                >
                    <SkipBack className="h-4 w-4" />
                </button>

                <button
                    onClick={() => setPlaying(!playing)}
                    className="p-2 bg-primary hover:bg-primary/90 rounded text-primary-foreground"
                >
                    {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                </button>

                <button
                    onClick={() => setCurrentFrame(Math.min(replayData.length - 1, currentFrame + 10))}
                    className="p-2 hover:bg-secondary rounded"
                >
                    <FastForward className="h-4 w-4" />
                </button>

                {/* Progress bar */}
                <div className="flex-1 h-1 bg-secondary rounded-full overflow-hidden">
                    <div
                        className="h-full bg-primary transition-all"
                        style={{ width: `${(currentFrame / Math.max(1, replayData.length - 1)) * 100}%` }}
                    />
                </div>

                <span className="text-xs text-muted-foreground font-mono">
                    {sessionId || 'Demo'}
                </span>
            </div>
        </div>
    );
}
