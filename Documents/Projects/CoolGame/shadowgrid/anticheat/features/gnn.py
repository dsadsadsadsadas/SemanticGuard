"""
ShadowGrid Graph Neural Network for Collusion Detection

Maps player interactions as graph and detects cheat collusion networks.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import numpy as np


@dataclass
class PlayerNode:
    """Node representing a player in the interaction graph."""
    player_id: str
    
    # Behavior metrics
    suspicion_score: float = 0.0
    total_interactions: int = 0
    crystals_collected: int = 0
    deaths: int = 0
    session_duration: float = 0.0
    
    # Embedding (will be learned)
    embedding: Optional[np.ndarray] = None


@dataclass
class InteractionEdge:
    """Edge representing interaction between players."""
    player_a: str
    player_b: str
    
    # Interaction metrics
    proximity_time: float = 0.0      # Time spent near each other
    mutual_assists: int = 0          # Times one helped the other
    crystal_shares: int = 0          # Crystals collected near each other
    collision_count: int = 0         # Times they collided/blocked
    
    # Temporal
    first_interaction: float = 0.0
    last_interaction: float = 0.0
    
    # Suspicious behaviors
    coordinated_moves: int = 0       # Moved in same direction simultaneously
    anti_competitive: int = 0        # Avoided competing for same crystal


class CollisionGraph:
    """
    Graph structure for player interactions.
    
    Detects:
    - Wintrading (intentional losing to boost partner)
    - Collusion (coordinated cheating)
    - Account networks (same person, multiple accounts)
    """
    
    def __init__(self):
        self.nodes: Dict[str, PlayerNode] = {}
        self.edges: Dict[Tuple[str, str], InteractionEdge] = {}
        
        # Adjacency list for efficient traversal
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)
    
    def add_player(self, player_id: str) -> PlayerNode:
        """Add or get a player node."""
        if player_id not in self.nodes:
            self.nodes[player_id] = PlayerNode(player_id=player_id)
        return self.nodes[player_id]
    
    def get_edge(self, player_a: str, player_b: str) -> InteractionEdge:
        """Get or create edge between players."""
        # Normalize edge key (smaller id first)
        key = (min(player_a, player_b), max(player_a, player_b))
        
        if key not in self.edges:
            self.edges[key] = InteractionEdge(
                player_a=key[0],
                player_b=key[1],
                first_interaction=time.time()
            )
            self.adjacency[key[0]].add(key[1])
            self.adjacency[key[1]].add(key[0])
        
        self.edges[key].last_interaction = time.time()
        return self.edges[key]
    
    def record_proximity(
        self,
        player_a: str,
        player_b: str,
        duration: float
    ) -> None:
        """Record time players spent near each other."""
        self.add_player(player_a)
        self.add_player(player_b)
        edge = self.get_edge(player_a, player_b)
        edge.proximity_time += duration
        
        # Update interaction counts
        self.nodes[player_a].total_interactions += 1
        self.nodes[player_b].total_interactions += 1
    
    def record_coordinated_move(self, player_a: str, player_b: str) -> None:
        """Record when players moved in coordination."""
        edge = self.get_edge(player_a, player_b)
        edge.coordinated_moves += 1
    
    def record_anti_competitive(self, player_a: str, player_b: str) -> None:
        """Record when players avoided competition."""
        edge = self.get_edge(player_a, player_b)
        edge.anti_competitive += 1
    
    def record_crystal_share(self, player_a: str, player_b: str) -> None:
        """Record when crystal collected near both players."""
        edge = self.get_edge(player_a, player_b)
        edge.crystal_shares += 1
    
    def update_player_suspicion(self, player_id: str, score: float) -> None:
        """Update a player's suspicion score."""
        if player_id in self.nodes:
            self.nodes[player_id].suspicion_score = score
    
    def detect_clusters(self) -> List[Set[str]]:
        """
        Detect clusters of potentially colluding players.
        
        Uses connected components where edge weight > threshold.
        """
        # Filter to strong edges
        strong_threshold = 5  # Minimum interactions
        strong_edges = {
            k: e for k, e in self.edges.items()
            if (e.coordinated_moves + e.anti_competitive) > strong_threshold
        }
        
        if not strong_edges:
            return []
        
        # Build filtered adjacency
        filtered_adj: Dict[str, Set[str]] = defaultdict(set)
        for (a, b), edge in strong_edges.items():
            filtered_adj[a].add(b)
            filtered_adj[b].add(a)
        
        # Find connected components
        visited = set()
        clusters = []
        
        for player in filtered_adj:
            if player in visited:
                continue
            
            # BFS to find component
            cluster = set()
            queue = [player]
            
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                
                visited.add(current)
                cluster.add(current)
                
                for neighbor in filtered_adj[current]:
                    if neighbor not in visited:
                        queue.append(neighbor)
            
            if len(cluster) > 1:  # Only clusters of 2+
                clusters.append(cluster)
        
        return clusters
    
    def get_collusion_score(self, player_a: str, player_b: str) -> float:
        """
        Calculate collusion likelihood between two players.
        
        Returns:
            Score from 0 (no collusion) to 1 (definite collusion)
        """
        key = (min(player_a, player_b), max(player_a, player_b))
        
        if key not in self.edges:
            return 0.0
        
        edge = self.edges[key]
        
        # Factors indicating collusion
        score = 0.0
        
        # Coordinated movement
        if edge.coordinated_moves > 10:
            score += min(0.3, edge.coordinated_moves / 100)
        
        # Anti-competitive behavior
        if edge.anti_competitive > 5:
            score += min(0.3, edge.anti_competitive / 50)
        
        # Excessive proximity
        if edge.proximity_time > 60:  # More than a minute together
            score += min(0.2, edge.proximity_time / 300)
        
        # Both players suspicious
        node_a = self.nodes.get(player_a)
        node_b = self.nodes.get(player_b)
        
        if node_a and node_b:
            if node_a.suspicion_score > 0.5 and node_b.suspicion_score > 0.5:
                score += 0.2
        
        return min(1.0, score)
    
    def get_node_features(self, player_id: str) -> np.ndarray:
        """
        Get feature vector for a player node.
        
        For use in GNN message passing.
        """
        node = self.nodes.get(player_id)
        if not node:
            return np.zeros(8, dtype=np.float32)
        
        features = np.array([
            node.suspicion_score,
            node.total_interactions / 100,
            node.crystals_collected / 50,
            node.deaths / 10,
            node.session_duration / 3600,
            len(self.adjacency.get(player_id, set())) / 10,  # Degree
            self._get_avg_neighbor_suspicion(player_id),
            self._get_clustering_coefficient(player_id)
        ], dtype=np.float32)
        
        return features
    
    def _get_avg_neighbor_suspicion(self, player_id: str) -> float:
        """Get average suspicion of neighbors."""
        neighbors = self.adjacency.get(player_id, set())
        if not neighbors:
            return 0.0
        
        scores = [
            self.nodes[n].suspicion_score
            for n in neighbors
            if n in self.nodes
        ]
        
        return np.mean(scores) if scores else 0.0
    
    def _get_clustering_coefficient(self, player_id: str) -> float:
        """Calculate local clustering coefficient."""
        neighbors = list(self.adjacency.get(player_id, set()))
        if len(neighbors) < 2:
            return 0.0
        
        # Count edges between neighbors
        neighbor_edges = 0
        for i, n1 in enumerate(neighbors):
            for n2 in neighbors[i+1:]:
                key = (min(n1, n2), max(n1, n2))
                if key in self.edges:
                    neighbor_edges += 1
        
        # Max possible edges between neighbors
        max_edges = len(neighbors) * (len(neighbors) - 1) / 2
        
        return neighbor_edges / max_edges if max_edges > 0 else 0.0
    
    def get_edge_features(self, player_a: str, player_b: str) -> np.ndarray:
        """Get feature vector for an edge."""
        key = (min(player_a, player_b), max(player_a, player_b))
        edge = self.edges.get(key)
        
        if not edge:
            return np.zeros(6, dtype=np.float32)
        
        # Duration of relationship
        duration = edge.last_interaction - edge.first_interaction
        
        features = np.array([
            edge.proximity_time / 300,
            edge.coordinated_moves / 50,
            edge.anti_competitive / 20,
            edge.crystal_shares / 20,
            duration / 3600,
            self.get_collusion_score(player_a, player_b)
        ], dtype=np.float32)
        
        return features
    
    def to_adjacency_matrix(self) -> Tuple[np.ndarray, List[str]]:
        """
        Convert graph to adjacency matrix.
        
        Returns:
            (adjacency_matrix, player_id_list)
        """
        player_ids = list(self.nodes.keys())
        n = len(player_ids)
        
        if n == 0:
            return np.zeros((0, 0)), []
        
        id_to_idx = {pid: i for i, pid in enumerate(player_ids)}
        
        adj = np.zeros((n, n), dtype=np.float32)
        
        for (a, b), edge in self.edges.items():
            if a in id_to_idx and b in id_to_idx:
                weight = self.get_collusion_score(a, b)
                adj[id_to_idx[a]][id_to_idx[b]] = weight
                adj[id_to_idx[b]][id_to_idx[a]] = weight
        
        return adj, player_ids
    
    def analyze(self) -> dict:
        """
        Perform full graph analysis.
        
        Returns:
            Analysis results including clusters and suspicious pairs
        """
        clusters = self.detect_clusters()
        
        # Find most suspicious pairs
        suspicious_pairs = []
        for (a, b), edge in self.edges.items():
            score = self.get_collusion_score(a, b)
            if score > 0.3:
                suspicious_pairs.append({
                    'players': (a, b),
                    'score': score,
                    'coordinated_moves': edge.coordinated_moves,
                    'anti_competitive': edge.anti_competitive,
                    'proximity_time': edge.proximity_time
                })
        
        suspicious_pairs.sort(key=lambda x: x['score'], reverse=True)
        
        return {
            'total_players': len(self.nodes),
            'total_edges': len(self.edges),
            'clusters': [list(c) for c in clusters],
            'suspicious_pairs': suspicious_pairs[:10],  # Top 10
            'avg_clustering_coef': self._get_global_clustering()
        }
    
    def _get_global_clustering(self) -> float:
        """Get global clustering coefficient."""
        if not self.nodes:
            return 0.0
        
        coeffs = [
            self._get_clustering_coefficient(pid)
            for pid in self.nodes
        ]
        
        return np.mean(coeffs)
