import { useState, useEffect, useRef } from 'react';
import { Eye, Radio, Users, Wifi, WifiOff } from 'lucide-react';

interface PlayerInfo {
    player_id: string;
    x: number;
    y: number;
    health: number;
    score: number;
    suspicion_score: number;
    ai_score?: number;
    ai_flagged?: boolean;
}

interface LlamaAnalysis {
    suspicion_level: string;
    confidence: number;
    reasoning: string;
    findings: string[];
}

interface GameState {
    tick: number;
    players: Record<string, PlayerInfo>;
}

export function SpectatorView() {
    const [connected, setConnected] = useState(false);
    const [activePlayers, setActivePlayers] = useState<string[]>([]);
    const [selectedPlayer, setSelectedPlayer] = useState<string | null>(null);
    const [gameState, setGameState] = useState<GameState | null>(null);
    const [gridData, setGridData] = useState<number[][] | null>(null);
    const [debugInfo, setDebugInfo] = useState<string>('');
    const [llamaAnalysis, setLlamaAnalysis] = useState<LlamaAnalysis | null>(null);
    const [analyzing, setAnalyzing] = useState(false);

    const playerCanvasRef = useRef<HTMLCanvasElement>(null);
    const serverCanvasRef = useRef<HTMLCanvasElement>(null);

    const GRID_SIZE = 20;
    const FOG_RADIUS = 3;

    // Fetch active players - runs independently
    useEffect(() => {
        const fetchPlayers = async () => {
            try {
                const res = await fetch('http://localhost:8000/players');
                const data = await res.json();
                const playerIds = data.players?.map((p: any) => p.player_id) || [];
                setActivePlayers(playerIds);

                // Auto-select first player if none selected
                if (playerIds.length > 0 && !selectedPlayer) {
                    setSelectedPlayer(playerIds[0]);
                }
            } catch (e) {
                console.error('Failed to fetch players:', e);
            }
        };

        fetchPlayers();
        const interval = setInterval(fetchPlayers, 2000);
        return () => clearInterval(interval);
    }, [selectedPlayer]);

    // Fetch game state - runs independently of player selection
    useEffect(() => {
        const fetchState = async () => {
            try {
                const res = await fetch('http://localhost:8000/game/state');
                const data = await res.json();

                const playerCount = Object.keys(data.players || {}).length;
                setDebugInfo(`Tick: ${data.tick} | Players: ${playerCount}`);

                if (playerCount > 0) {
                    setGameState({
                        tick: data.tick,
                        players: data.players || {}
                    });
                    setConnected(true);
                } else {
                    setConnected(false);
                }
            } catch (e) {
                setConnected(false);
                setDebugInfo('API Error');
            }
        };

        fetchState();
        const interval = setInterval(fetchState, 200); // 5 FPS - more stable
        return () => clearInterval(interval);
    }, []);

    // Fetch grid data (walls, lava, crystals) - once on mount
    useEffect(() => {
        const fetchGrid = async () => {
            try {
                const res = await fetch('http://localhost:8000/game/grid');
                const data = await res.json();
                setGridData(data.grid || null);
            } catch (e) {
                console.error('Failed to fetch grid:', e);
            }
        };
        fetchGrid();
        // Refresh grid every 5s in case it changes
        const interval = setInterval(fetchGrid, 5000);
        return () => clearInterval(interval);
    }, []);

    // Draw BOTH canvases whenever gameState changes
    useEffect(() => {
        if (!gameState) return;

        drawPlayerView();
        drawServerView();
    }, [gameState, selectedPlayer]);

    const drawPlayerView = () => {
        const canvas = playerCanvasRef.current;
        if (!canvas || !gameState || !selectedPlayer) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const player = gameState.players[selectedPlayer];
        if (!player) {
            // Draw "player disconnected" message
            ctx.fillStyle = '#0a0a0a';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#666';
            ctx.font = '14px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Player disconnected', canvas.width / 2, canvas.height / 2);
            return;
        }

        const cellSize = canvas.width / (FOG_RADIUS * 2 + 1);

        // Clear
        ctx.fillStyle = '#0a0a0a';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Draw fog-limited view
        for (let dy = -FOG_RADIUS; dy <= FOG_RADIUS; dy++) {
            for (let dx = -FOG_RADIUS; dx <= FOG_RADIUS; dx++) {
                const worldX = player.x + dx;
                const worldY = player.y + dy;
                const canvasX = (dx + FOG_RADIUS) * cellSize;
                const canvasY = (dy + FOG_RADIUS) * cellSize;

                // Calculate fog intensity based on distance
                const dist = Math.sqrt(dx * dx + dy * dy);
                const fogAlpha = Math.min(1, dist / FOG_RADIUS) * 0.7;

                // Draw tile
                ctx.fillStyle = '#1a1a2e';
                ctx.fillRect(canvasX, canvasY, cellSize - 1, cellSize - 1);

                // Apply fog
                ctx.fillStyle = `rgba(0, 0, 0, ${fogAlpha})`;
                ctx.fillRect(canvasX, canvasY, cellSize, cellSize);

                // Draw player at center
                if (dx === 0 && dy === 0) {
                    ctx.fillStyle = '#22c55e';
                    ctx.beginPath();
                    ctx.arc(canvasX + cellSize / 2, canvasY + cellSize / 2, cellSize / 3, 0, Math.PI * 2);
                    ctx.fill();
                }

                // Draw other players if visible
                Object.entries(gameState.players).forEach(([pid, p]) => {
                    if (pid !== selectedPlayer && p.x === worldX && p.y === worldY) {
                        ctx.fillStyle = '#3b82f6';
                        ctx.beginPath();
                        ctx.arc(canvasX + cellSize / 2, canvasY + cellSize / 2, cellSize / 4, 0, Math.PI * 2);
                        ctx.fill();
                    }
                });
            }
        }

        // Label
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('PLAYER VIEW', 10, 20);
        ctx.font = '10px sans-serif';
        ctx.fillStyle = '#666';
        ctx.fillText(`(${player.x}, ${player.y})`, 10, 35);
    };

    const drawServerView = () => {
        const canvas = serverCanvasRef.current;
        if (!canvas || !gameState) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const cellSize = canvas.width / GRID_SIZE;

        // Clear
        ctx.fillStyle = '#0a0a0a';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Draw grid
        ctx.strokeStyle = '#1a1a2e';
        ctx.lineWidth = 0.5;
        for (let i = 0; i <= GRID_SIZE; i++) {
            ctx.beginPath();
            ctx.moveTo(i * cellSize, 0);
            ctx.lineTo(i * cellSize, canvas.height);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(0, i * cellSize);
            ctx.lineTo(canvas.width, i * cellSize);
            ctx.stroke();
        }

        // Draw hazards (lava = 2, walls = 1, crystals = 3)
        // Tile types: 0=floor, 1=wall, 2=lava, 3=crystal, 4=spawn
        if (gridData) {
            for (let y = 0; y < Math.min(GRID_SIZE, gridData.length); y++) {
                for (let x = 0; x < Math.min(GRID_SIZE, gridData[y]?.length || 0); x++) {
                    const tile = gridData[y][x];
                    const px = x * cellSize;
                    const py = y * cellSize;

                    if (tile === 2) {
                        // LAVA - orange/red glow
                        ctx.fillStyle = 'rgba(255, 80, 20, 0.7)';
                        ctx.fillRect(px + 1, py + 1, cellSize - 2, cellSize - 2);
                        // Glow effect
                        ctx.shadowColor = '#ff5014';
                        ctx.shadowBlur = 5;
                        ctx.fillStyle = 'rgba(255, 150, 50, 0.4)';
                        ctx.fillRect(px + 3, py + 3, cellSize - 6, cellSize - 6);
                        ctx.shadowBlur = 0;
                    } else if (tile === 1) {
                        // WALL - dark gray
                        ctx.fillStyle = 'rgba(60, 60, 80, 0.8)';
                        ctx.fillRect(px, py, cellSize, cellSize);
                    } else if (tile === 3) {
                        // CRYSTAL - cyan sparkle
                        ctx.fillStyle = 'rgba(0, 255, 255, 0.6)';
                        ctx.beginPath();
                        ctx.arc(px + cellSize / 2, py + cellSize / 2, cellSize / 4, 0, Math.PI * 2);
                        ctx.fill();
                    }
                }
            }
        }

        // Draw ALL players
        const playerEntries = Object.entries(gameState.players);

        playerEntries.forEach(([pid, p]) => {
            const x = p.x * cellSize + cellSize / 2;
            const y = p.y * cellSize + cellSize / 2;

            // Suspicion heatmap (red glow)
            const suspicion = p.suspicion_score || 0;
            if (suspicion > 30) {
                const gradient = ctx.createRadialGradient(x, y, 0, x, y, cellSize * 2);
                gradient.addColorStop(0, `rgba(239, 68, 68, ${suspicion / 100})`);
                gradient.addColorStop(1, 'transparent');
                ctx.fillStyle = gradient;
                ctx.fillRect(x - cellSize * 2, y - cellSize * 2, cellSize * 4, cellSize * 4);
            }

            // Player dot
            const isSelected = pid === selectedPlayer;
            ctx.fillStyle = isSelected ? '#22c55e' : '#3b82f6';
            ctx.beginPath();
            ctx.arc(x, y, cellSize / 3, 0, Math.PI * 2);
            ctx.fill();

            // Player label
            ctx.fillStyle = '#fff';
            ctx.font = '8px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(pid.substring(0, 8), x, y + cellSize);

            // Suspicion indicator
            if (suspicion > 50) {
                ctx.fillStyle = '#ef4444';
                ctx.font = 'bold 10px sans-serif';
                ctx.fillText('⚠️', x + cellSize, y - cellSize / 2);
            }
        });

        // Label + debug
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('SERVER TRUTH', 10, 20);
        ctx.font = '10px sans-serif';
        ctx.fillStyle = '#22c55e';
        ctx.fillText(`${playerEntries.length} players`, 10, 35);
    };

    return (
        <div className="flex flex-col h-full bg-background">
            {/* Header */}
            <div className="p-6 border-b border-border flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-bold tracking-tight flex items-center gap-2">
                        <Radio className="h-5 w-5 text-primary animate-pulse" />
                        Live Feed
                    </h2>
                    <p className="text-sm text-muted-foreground mt-1">
                        {debugInfo || 'Connecting...'}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {connected ? (
                        <span className="flex items-center gap-2 text-green-500 text-sm">
                            <Wifi className="h-4 w-4" />
                            Live
                        </span>
                    ) : (
                        <span className="flex items-center gap-2 text-yellow-500 text-sm">
                            <WifiOff className="h-4 w-4" />
                            No players
                        </span>
                    )}
                </div>
            </div>

            <div className="flex-1 flex overflow-hidden">
                {/* Player List Sidebar */}
                <div className="w-64 border-r border-border p-4 overflow-auto">
                    <h3 className="font-semibold text-sm text-muted-foreground mb-3 flex items-center gap-2">
                        <Users className="h-4 w-4" />
                        Active Players ({activePlayers.length})
                    </h3>

                    {activePlayers.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <Eye className="h-8 w-8 mx-auto mb-2 opacity-50" />
                            <p className="text-sm">No active players</p>
                            <p className="text-xs mt-1">Run the demo:</p>
                            <code className="text-xs bg-secondary px-2 py-1 rounded mt-2 block">
                                python run_demo.py
                            </code>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {activePlayers.map(pid => (
                                <button
                                    key={pid}
                                    onClick={() => setSelectedPlayer(pid)}
                                    className={`w-full text-left p-3 rounded-lg border transition-all ${selectedPlayer === pid
                                        ? 'border-primary bg-primary/10'
                                        : 'border-border hover:border-primary/50 hover:bg-secondary/50'
                                        }`}
                                >
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="font-medium text-sm">{pid}</span>
                                        {gameState?.players[pid] && (
                                            <span className={`text-xs font-mono ${(gameState.players[pid].suspicion_score || 0) > 50
                                                ? 'text-destructive'
                                                : 'text-muted-foreground'
                                                }`}>
                                                {(gameState.players[pid].suspicion_score || 0).toFixed(0)}%
                                            </span>
                                        )}
                                    </div>
                                    {/* HP Bar */}
                                    {gameState?.players[pid] && (
                                        <div className="flex items-center gap-2">
                                            <span className="text-xs text-red-400">❤️</span>
                                            <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                                                <div
                                                    className="h-full rounded-full transition-all"
                                                    style={{
                                                        width: `${gameState.players[pid].health || 100}%`,
                                                        background: (gameState.players[pid].health || 100) > 50
                                                            ? '#22c55e'
                                                            : (gameState.players[pid].health || 100) > 25
                                                                ? '#fbbf24'
                                                                : '#ef4444'
                                                    }}
                                                />
                                            </div>
                                            <span className="text-xs text-muted-foreground w-8">
                                                {gameState.players[pid].health || 100}
                                            </span>
                                        </div>
                                    )}
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {/* Spectator Area */}
                <div className="flex-1 p-6">
                    {!selectedPlayer ? (
                        <div className="h-full flex items-center justify-center text-muted-foreground">
                            <div className="text-center">
                                <Eye className="h-16 w-16 mx-auto mb-4 opacity-30" />
                                <p className="font-medium">Select a player to spectate</p>
                            </div>
                        </div>
                    ) : (
                        <div className="h-full flex flex-col">
                            {/* Player Info Bar */}
                            <div className="mb-4 p-4 rounded-lg border border-border bg-card flex items-center justify-between">
                                <div className="flex items-center gap-4">
                                    <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center">
                                        <Eye className="h-5 w-5 text-primary" />
                                    </div>
                                    <div>
                                        <p className="font-bold">{selectedPlayer}</p>
                                        <p className="text-xs text-muted-foreground">
                                            Tick: {gameState?.tick || 0}
                                        </p>
                                    </div>
                                </div>

                                {gameState?.players[selectedPlayer] && (
                                    <div className="flex items-center gap-6">
                                        <div className="text-center">
                                            <p className="text-xs text-muted-foreground">Position</p>
                                            <p className="font-mono font-bold">
                                                ({gameState.players[selectedPlayer].x}, {gameState.players[selectedPlayer].y})
                                            </p>
                                        </div>
                                        <div className="text-center">
                                            <p className="text-xs text-muted-foreground">Suspicion (AI)</p>
                                            <p className={`font-bold ${(gameState.players[selectedPlayer].ai_score || 0) > 50
                                                ? 'text-destructive'
                                                : 'text-green-500'
                                                }`}>
                                                {(gameState.players[selectedPlayer].ai_score || gameState.players[selectedPlayer].suspicion_score || 0).toFixed(0)}%
                                            </p>
                                        </div>
                                        <div className="flex flex-col gap-1">
                                            <button
                                                className="px-3 py-1 bg-primary text-primary-foreground text-xs rounded hover:bg-primary/90 disabled:opacity-50"
                                                disabled={analyzing}
                                                onClick={async () => {
                                                    setAnalyzing(true);
                                                    try {
                                                        const res = await fetch(`http://localhost:8000/ai/analyze/${selectedPlayer}`, { method: 'POST' });
                                                        const data = await res.json();
                                                        if (data.reasoning) { // API returns 'reasoning', 'findings'
                                                            alert(`🧠 AI Analysis:\n\n${data.reasoning}`);
                                                        } else if (data.llama_reasoning) {
                                                            alert(`🧠 AI Analysis:\n\n${data.llama_reasoning}`);
                                                        } else {
                                                            alert('Analysis failed or returned no data');
                                                        }
                                                    } catch (e) {
                                                        alert('Error calling AI analysis');
                                                    }
                                                    setAnalyzing(false);
                                                }}
                                            >
                                                {analyzing ? 'Thinking...' : '🧠 Deep Analyze'}
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>

                            {/* Split View */}
                            <div className="flex-1 grid grid-cols-2 gap-4">
                                {/* Player View */}
                                <div className="rounded-lg border border-border bg-black overflow-hidden">
                                    <canvas
                                        ref={playerCanvasRef}
                                        width={400}
                                        height={400}
                                        className="w-full h-full"
                                    />
                                </div>

                                {/* Server View */}
                                <div className="rounded-lg border border-primary/30 bg-black overflow-hidden relative">
                                    <canvas
                                        ref={serverCanvasRef}
                                        width={400}
                                        height={400}
                                        className="w-full h-full"
                                    />
                                    <div className="absolute top-2 right-2 bg-primary/20 px-2 py-1 rounded text-xs font-bold text-primary">
                                        ADMIN VIEW
                                    </div>
                                </div>
                            </div>

                            {/* Legend */}
                            <div className="mt-4 flex items-center justify-center gap-6 text-xs text-muted-foreground">
                                <div className="flex items-center gap-2">
                                    <div className="h-3 w-3 rounded-full bg-green-500" />
                                    <span>Selected Player</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <div className="h-3 w-3 rounded-full bg-blue-500" />
                                    <span>Other Players</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <div className="h-3 w-3 rounded-full bg-red-500/50" />
                                    <span>Suspicion Heatmap</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div >
    );
}
