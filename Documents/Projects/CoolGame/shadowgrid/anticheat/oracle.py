"""
The Oracle: Layer 2 Detection (Decision Quality Analysis)
Catches Gen 5 bots "The Ghost" / SusPlayer_5 by detecting "God Mode" pathfinding.
"""
from heapq import heappush, heappop
from typing import List, Tuple, Set, Optional
from ..game.world import Grid, TileType

class DecisionQualityAnalyzer:
    """
    Analyzes decision quality by comparing player moves against A* optimal paths.
    """
    
    def __init__(self):
        self.total_moves = 0
        self.optimal_moves = 0
        
        # Thresholds (Tuned for Operation Double Tap)
        self.MIN_MOVES_THRESHOLD = 10  # Lowered from 25 to catch rapid bots
        self.GOD_MODE_THRESHOLD = 0.90 # Forensic Fix: Lowered from 0.95 to catch replay attacks
        self.CRITICAL_THRESHOLD = 0.98 # > 98% optimal (Instant Ban for short sessions)
        self.PRO_THRESHOLD = 0.70      # > 70% optimal
        
    def analyze_move(
        self, 
        grid: Grid, 
        start: Tuple[int, int], 
        end: Tuple[int, int]
    ) -> bool:
        """
        Analyze if a move was optimal.
        
        Args:
            grid: The game grid snapshot
            start: Player position before move
            end: Player position after move
            
        Returns:
            True if move lies on an optimal path to nearest crystal
        """
        # Find all crystals
        crystals = []
        for y in range(grid.height):
            for x in range(grid.width):
                if grid.tiles[y][x].tile_type == TileType.CRYSTAL:
                    crystals.append((x, y))
                    
        if not crystals:
            # No objective, optimization undefined. Assume optimal to avoid penalty.
            self.total_moves += 1
            self.optimal_moves += 1
            return True
            
        # Find nearest crystal (Manhattan distance heuristic for target selection)
        target = min(crystals, key=lambda p: abs(p[0]-start[0]) + abs(p[1]-start[1]))
        
        # Run A* to find optimal path
        path = self._astar(grid, start, target)
        
        # Determine if move matches optimal path
        is_optimal = False
        
        if len(path) > 1:
            # path[0] is start, path[1] is the optimal next step
            # If end matches path[1], it's optimal.
            if path[1] == end:
                is_optimal = True
        elif start == target:
            is_optimal = True
            
        self.total_moves += 1
        if is_optimal:
            self.optimal_moves += 1
            
        return is_optimal

    def get_verdict(self) -> str:
        """Get the classification based on optimality ratio."""
        if self.total_moves < self.MIN_MOVES_THRESHOLD:
            # CHECK FOR EARLY EXIT (SusPlayer_5 Strategy)
            # If they have > 10 moves and are PERFECT, flag them.
            if self.total_moves > 10:
                ratio = self.optimal_moves / self.total_moves
                if ratio > self.CRITICAL_THRESHOLD:
                    return "GOD_MODE"
            return "INSUFFICIENT_DATA"
            
        ratio = self.optimal_moves / self.total_moves
        
        if ratio > self.GOD_MODE_THRESHOLD:
            return "GOD_MODE"
        elif ratio > self.PRO_THRESHOLD:
            return "PRO_HUMAN"
        elif ratio < 0.5:
            return "NOOB"
            
        return "LEGIT"
            
    def get_score(self) -> float:
        """Get the optimality ratio (0.0 - 1.0)."""
        if self.total_moves == 0:
            return 0.0
        return self.optimal_moves / self.total_moves

    def _astar(self, grid: Grid, start: Tuple[int, int], goal: Tuple[int, int]) -> List[Tuple[int, int]]:
        """Compute A* path from start to goal."""
        def heuristic(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        frontier = []
        heappush(frontier, (0, start))
        came_from = {start: None}
        cost_so_far = {start: 0}
        
        while frontier:
            current = heappop(frontier)[1]
            
            if current == goal:
                break
            
            x, y = current
            # Explore neighbors
            neighbors = []
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < grid.width and 0 <= ny < grid.height:
                    tile = grid.tiles[ny][nx]
                    if tile.tile_type not in (TileType.WALL, TileType.LAVA):
                        neighbors.append((nx, ny))
            
            for next_node in neighbors:
                new_cost = cost_so_far[current] + 1
                if next_node not in cost_so_far or new_cost < cost_so_far[next_node]:
                    cost_so_far[next_node] = new_cost
                    priority = new_cost + heuristic(next_node, goal)
                    heappush(frontier, (priority, next_node))
                    came_from[next_node] = current
                    
        # Reconstruct path
        if goal not in came_from:
            return [] # No path found
            
        path = []
        current = goal
        while current != start:
            path.append(current)
            current = came_from[current]
        path.append(start)
        path.reverse()
        return path
