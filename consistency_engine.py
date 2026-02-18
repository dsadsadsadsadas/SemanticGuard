#!/usr/bin/env python3
"""
🔮 TREPAN Consistency Engine (TR-11)
Cognitive Sanity Layer for GEMINI.md.

Detects:
- Conflicting Diamonds (opposing directives on same topic)
- Duplicate Diamonds (redundant rules)
- Stale Diamonds (old, unreferenced entries)

DESIGN PHILOSOPHY:
- Memory without cleanup is hoarding
- Contradiction must be visible, not hidden
- Humans resolve conflicts — tools surface them
- Stability beats cleverness

NO AUTO-DELETE. EVER.
"""

import os
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

GEMINI_FILE = "GEMINI.md"
STALE_DAYS_THRESHOLD = 30  # Days before a Diamond is considered stale


@dataclass
class Diamond:
    """Parsed Diamond from GEMINI.md."""
    id: str
    timestamp: Optional[datetime]
    intent_law: str
    intent_why: str
    body: str
    tags: List[str] = field(default_factory=list)
    phase: Optional[str] = None
    drift_score: Optional[float] = None
    line_start: int = 0
    line_end: int = 0


@dataclass
class Conflict:
    """Detected conflict between two Diamonds."""
    cluster: str
    diamond_a: str
    diamond_b: str
    similarity: float
    reason: str


@dataclass
class Duplicate:
    """Detected duplicate Diamonds."""
    diamond_ids: List[str]
    similarity: float
    suggested_action: str = "MERGE"


@dataclass
class StaleEntry:
    """Detected stale Diamond."""
    diamond_id: str
    age_days: int
    timestamp: Optional[datetime]


@dataclass
class Cluster:
    """Semantic cluster of related Diamonds."""
    name: str
    diamond_ids: List[str]
    dominant_tags: List[str]


@dataclass
class ConsistencyReport:
    """Full consistency analysis report."""
    conflicts: List[Conflict]
    duplicates: List[Duplicate]
    stale: List[StaleEntry]
    clusters: List[Cluster]
    total_diamonds: int
    analysis_timestamp: str


class ConsistencyEngine:
    """
    Analyzes GEMINI.md for contradictions, duplication, and cognitive decay.
    
    Uses existing Drift Engine embeddings for semantic analysis.
    No LLM calls. Deterministic output only.
    """
    
    # Strong polarity keywords
    STRONG_POSITIVE = {"always", "must", "require", "mandatory", "enforce"}
    STRONG_NEGATIVE = {"never", "forbidden", "disallow", "prohibit", "block"}
    WEAK_POSITIVE = {"prefer", "recommend", "should", "usually", "favor"}
    WEAK_NEGATIVE = {"avoid", "discourage", "minimize", "limit"}
    
    def __init__(self, gemini_path: str = GEMINI_FILE):
        self.gemini_path = gemini_path
        self.logger = logging.getLogger("Trepan.Consistency")
        self.diamonds: List[Diamond] = []
        self._embeddings_cache: Dict[str, Any] = {}
        
        # Try to load Drift Engine
        try:
            from drift_engine import drift_monitor
            self.drift_engine = drift_monitor
            self.has_embeddings = drift_monitor.is_ready
        except ImportError:
            self.drift_engine = None
            self.has_embeddings = False
    
    def analyze(self) -> ConsistencyReport:
        """
        Run full consistency analysis on GEMINI.md.
        
        Returns:
            ConsistencyReport with conflicts, duplicates, stale entries, and clusters
        """
        self.logger.info("[*] Starting consistency analysis...")
        
        # Step 1: Parse GEMINI.md
        self.diamonds = self._parse_gemini()
        self.logger.info(f"[*] Parsed {len(self.diamonds)} Diamonds")
        
        if len(self.diamonds) < 2:
            return ConsistencyReport(
                conflicts=[],
                duplicates=[],
                stale=[],
                clusters=[],
                total_diamonds=len(self.diamonds),
                analysis_timestamp=datetime.now().isoformat()
            )
        
        # Step 2: Build embeddings
        self._build_embeddings()
        
        # Step 3: Cluster Diamonds
        clusters = self._cluster_diamonds()
        
        # Step 4: Detect conflicts within clusters
        conflicts = self._detect_conflicts(clusters)
        
        # Step 5: Detect duplicates
        duplicates = self._detect_duplicates()
        
        # Step 6: Detect stale entries
        stale = self._detect_stale()
        
        report = ConsistencyReport(
            conflicts=conflicts,
            duplicates=duplicates,
            stale=stale,
            clusters=clusters,
            total_diamonds=len(self.diamonds),
            analysis_timestamp=datetime.now().isoformat()
        )
        
        self.logger.info(f"[*] Analysis complete: {len(conflicts)} conflicts, "
                        f"{len(duplicates)} duplicate groups, {len(stale)} stale")
        
        return report
    
    def _parse_gemini(self) -> List[Diamond]:
        """Parse GEMINI.md and extract all Diamonds."""
        if not os.path.exists(self.gemini_path):
            return []
        
        try:
            with open(self.gemini_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.logger.error(f"Failed to read GEMINI.md: {e}")
            return []
        
        diamonds = []
        lines = content.split("\n")
        
        # Regex patterns
        diamond_header = re.compile(r"##\s*💎\s*\[([^\]]+)\]\s*-\s*Intent:\s*(.+)")
        timestamp_pattern = re.compile(r"\*\*Timestamp:\*\*\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})")
        phase_pattern = re.compile(r"`phase`\s*\|\s*([^\|]+)\s*\|")
        drift_pattern = re.compile(r"\*\*Drift Score:\*\*\s*([\d.]+)")
        
        i = 0
        while i < len(lines):
            line = lines[i]
            match = diamond_header.match(line.strip())
            
            if match:
                diamond_id = match.group(1).strip()
                intent_law = match.group(2).strip()
                line_start = i
                
                # Collect body until next Diamond or EOF
                body_lines = []
                timestamp = None
                phase = None
                drift_score = None
                intent_why = ""
                
                i += 1
                while i < len(lines):
                    current = lines[i]
                    
                    # Check for next Diamond
                    if diamond_header.match(current.strip()):
                        break
                    
                    # Check for next section marker
                    if current.strip().startswith("---") and i > line_start + 1:
                        break
                    
                    body_lines.append(current)
                    
                    # Extract timestamp
                    ts_match = timestamp_pattern.search(current)
                    if ts_match:
                        try:
                            timestamp = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            pass
                    
                    # Extract phase
                    phase_match = phase_pattern.search(current)
                    if phase_match:
                        phase = phase_match.group(1).strip()
                    
                    # Extract drift score
                    drift_match = drift_pattern.search(current)
                    if drift_match:
                        try:
                            drift_score = float(drift_match.group(1))
                        except ValueError:
                            pass
                    
                    # Extract "The Why"
                    if "**🤔 The Why:**" in current or "The Why:" in current:
                        # Next non-empty line is the why
                        j = i + 1
                        while j < len(lines) and not lines[j].strip():
                            j += 1
                        if j < len(lines) and not lines[j].startswith("**"):
                            intent_why = lines[j].strip()
                    
                    i += 1
                
                body = "\n".join(body_lines)
                
                # Extract tags from body
                tags = self._extract_tags(body + " " + intent_law)
                
                diamonds.append(Diamond(
                    id=diamond_id,
                    timestamp=timestamp,
                    intent_law=intent_law,
                    intent_why=intent_why,
                    body=body,
                    tags=tags,
                    phase=phase,
                    drift_score=drift_score,
                    line_start=line_start,
                    line_end=i - 1
                ))
            else:
                i += 1
        
        return diamonds
    
    def _extract_tags(self, text: str) -> List[str]:
        """Extract semantic tags from text."""
        text_lower = text.lower()
        tags = []
        
        tag_patterns = {
            "auth": ["auth", "login", "password", "token", "session"],
            "database": ["sql", "database", "query", "postgres", "sqlite", "mongo"],
            "api": ["api", "endpoint", "request", "response", "http"],
            "security": ["security", "secure", "encrypt", "hash", "secret"],
            "config": ["config", "setting", "env", "environment"],
            "error": ["error", "exception", "try", "catch", "handle"],
            "test": ["test", "assert", "mock", "spec"],
            "ui": ["ui", "frontend", "component", "render", "display"],
            "performance": ["performance", "optimize", "cache", "memory"],
        }
        
        for tag, patterns in tag_patterns.items():
            if any(p in text_lower for p in patterns):
                tags.append(tag)
        
        return tags
    
    def _build_embeddings(self):
        """Build embeddings for all Diamonds using Drift Engine."""
        if not self.has_embeddings or not self.drift_engine:
            self.logger.warning("Embeddings not available, using tag-based clustering")
            return
        
        for diamond in self.diamonds:
            # Create text representation
            text = f"{diamond.intent_law} {diamond.intent_why} {diamond.body[:500]}"
            try:
                embedding = self.drift_engine.get_embedding(text)
                self._embeddings_cache[diamond.id] = embedding
            except Exception as e:
                self.logger.warning(f"Failed to embed Diamond {diamond.id}: {e}")
    
    def _compute_similarity(self, id_a: str, id_b: str) -> float:
        """Compute similarity between two Diamonds."""
        if id_a in self._embeddings_cache and id_b in self._embeddings_cache:
            try:
                import numpy as np
                emb_a = self._embeddings_cache[id_a]
                emb_b = self._embeddings_cache[id_b]
                
                # Cosine similarity
                dot = np.dot(emb_a, emb_b)
                norm_a = np.linalg.norm(emb_a)
                norm_b = np.linalg.norm(emb_b)
                
                if norm_a > 0 and norm_b > 0:
                    return float(dot / (norm_a * norm_b))
            except Exception:
                pass
        
        # Fallback: tag-based similarity
        diamond_a = next((d for d in self.diamonds if d.id == id_a), None)
        diamond_b = next((d for d in self.diamonds if d.id == id_b), None)
        
        if diamond_a and diamond_b:
            tags_a = set(diamond_a.tags)
            tags_b = set(diamond_b.tags)
            if tags_a or tags_b:
                intersection = len(tags_a & tags_b)
                union = len(tags_a | tags_b)
                return intersection / union if union > 0 else 0.0
        
        return 0.0
    
    def _cluster_diamonds(self) -> List[Cluster]:
        """Group Diamonds by semantic similarity (≥0.75)."""
        clusters: Dict[str, List[str]] = defaultdict(list)
        assigned = set()
        
        for i, diamond in enumerate(self.diamonds):
            if diamond.id in assigned:
                continue
            
            # Start new cluster
            cluster_diamonds = [diamond.id]
            assigned.add(diamond.id)
            
            # Find similar Diamonds
            for j in range(i + 1, len(self.diamonds)):
                other = self.diamonds[j]
                if other.id in assigned:
                    continue
                
                similarity = self._compute_similarity(diamond.id, other.id)
                if similarity >= 0.75:
                    cluster_diamonds.append(other.id)
                    assigned.add(other.id)
            
            # Determine cluster name from dominant tags
            all_tags = []
            for did in cluster_diamonds:
                d = next((x for x in self.diamonds if x.id == did), None)
                if d:
                    all_tags.extend(d.tags)
            
            if all_tags:
                from collections import Counter
                dominant = Counter(all_tags).most_common(2)
                cluster_name = dominant[0][0] if dominant else "general"
            else:
                cluster_name = f"cluster_{len(clusters)}"
            
            # Ensure unique cluster names
            if cluster_name in clusters:
                cluster_name = f"{cluster_name}_{len(clusters)}"
            
            clusters[cluster_name] = cluster_diamonds
        
        return [
            Cluster(
                name=name,
                diamond_ids=ids,
                dominant_tags=self._get_dominant_tags(ids)
            )
            for name, ids in clusters.items()
            if len(ids) > 0
        ]
    
    def _get_dominant_tags(self, diamond_ids: List[str]) -> List[str]:
        """Get most common tags across a set of Diamonds."""
        all_tags = []
        for did in diamond_ids:
            d = next((x for x in self.diamonds if x.id == did), None)
            if d:
                all_tags.extend(d.tags)
        
        if not all_tags:
            return []
        
        from collections import Counter
        return [tag for tag, _ in Counter(all_tags).most_common(3)]
    
    def _get_polarity(self, text: str) -> Tuple[str, str]:
        """
        Determine directive polarity.
        
        Returns:
            (direction, strength) where direction is "POSITIVE" or "NEGATIVE"
            and strength is "STRONG" or "WEAK"
        """
        text_lower = text.lower()
        
        for word in self.STRONG_POSITIVE:
            if word in text_lower:
                return ("POSITIVE", "STRONG")
        
        for word in self.STRONG_NEGATIVE:
            if word in text_lower:
                return ("NEGATIVE", "STRONG")
        
        for word in self.WEAK_POSITIVE:
            if word in text_lower:
                return ("POSITIVE", "WEAK")
        
        for word in self.WEAK_NEGATIVE:
            if word in text_lower:
                return ("NEGATIVE", "WEAK")
        
        return ("NEUTRAL", "NONE")
    
    def _detect_conflicts(self, clusters: List[Cluster]) -> List[Conflict]:
        """Detect conflicting Diamonds within clusters."""
        conflicts = []
        
        for cluster in clusters:
            if len(cluster.diamond_ids) < 2:
                continue
            
            # O(n²) within cluster
            for i, id_a in enumerate(cluster.diamond_ids):
                diamond_a = next((d for d in self.diamonds if d.id == id_a), None)
                if not diamond_a:
                    continue
                
                for j in range(i + 1, len(cluster.diamond_ids)):
                    id_b = cluster.diamond_ids[j]
                    diamond_b = next((d for d in self.diamonds if d.id == id_b), None)
                    if not diamond_b:
                        continue
                    
                    similarity = self._compute_similarity(id_a, id_b)
                    
                    # Check for conflict: similar topic but opposing polarity
                    if similarity >= 0.6:
                        polarity_a = self._get_polarity(diamond_a.intent_law + " " + diamond_a.body)
                        polarity_b = self._get_polarity(diamond_b.intent_law + " " + diamond_b.body)
                        
                        # Conflict if one is POSITIVE and other is NEGATIVE
                        if polarity_a[0] != polarity_b[0] and polarity_a[0] != "NEUTRAL" and polarity_b[0] != "NEUTRAL":
                            reason = f"Opposing {polarity_a[1].lower()}/{polarity_b[1].lower()} directives on same topic"
                            conflicts.append(Conflict(
                                cluster=cluster.name,
                                diamond_a=id_a,
                                diamond_b=id_b,
                                similarity=similarity,
                                reason=reason
                            ))
        
        return conflicts
    
    def _detect_duplicates(self) -> List[Duplicate]:
        """Detect Diamonds that are likely duplicates (≥0.85 similarity, same polarity)."""
        duplicates = []
        checked_pairs = set()
        
        for i, diamond_a in enumerate(self.diamonds):
            group = [diamond_a.id]
            
            for j in range(i + 1, len(self.diamonds)):
                diamond_b = self.diamonds[j]
                pair_key = tuple(sorted([diamond_a.id, diamond_b.id]))
                
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                
                similarity = self._compute_similarity(diamond_a.id, diamond_b.id)
                
                if similarity >= 0.85:
                    polarity_a = self._get_polarity(diamond_a.intent_law)
                    polarity_b = self._get_polarity(diamond_b.intent_law)
                    
                    # Same polarity = likely duplicate
                    if polarity_a[0] == polarity_b[0]:
                        group.append(diamond_b.id)
            
            if len(group) > 1:
                # Avoid reporting subsets
                existing_ids = set()
                for dup in duplicates:
                    existing_ids.update(dup.diamond_ids)
                
                if not any(did in existing_ids for did in group):
                    duplicates.append(Duplicate(
                        diamond_ids=group,
                        similarity=0.85
                    ))
        
        return duplicates
    
    def _detect_stale(self) -> List[StaleEntry]:
        """Detect Diamonds older than threshold."""
        stale = []
        cutoff = datetime.now() - timedelta(days=STALE_DAYS_THRESHOLD)
        
        for diamond in self.diamonds:
            if diamond.timestamp and diamond.timestamp < cutoff:
                age = (datetime.now() - diamond.timestamp).days
                stale.append(StaleEntry(
                    diamond_id=diamond.id,
                    age_days=age,
                    timestamp=diamond.timestamp
                ))
        
        return stale
    
    def format_report(self, report: ConsistencyReport) -> str:
        """Format report for CLI display."""
        lines = []
        lines.append("=" * 60)
        lines.append("🔮 TREPAN CONSISTENCY REPORT")
        lines.append(f"   Analyzed: {report.total_diamonds} Diamonds")
        lines.append(f"   Timestamp: {report.analysis_timestamp}")
        lines.append("=" * 60)
        
        # Conflicts
        lines.append(f"\n⚔️ CONFLICTS ({len(report.conflicts)})")
        lines.append("-" * 40)
        if report.conflicts:
            for c in report.conflicts:
                lines.append(f"  [{c.diamond_a}] ↔ [{c.diamond_b}]")
                lines.append(f"     Cluster: {c.cluster}")
                lines.append(f"     Similarity: {c.similarity:.2f}")
                lines.append(f"     Reason: {c.reason}")
                lines.append("")
        else:
            lines.append("  No conflicts detected ✅")
        
        # Duplicates
        lines.append(f"\n📋 DUPLICATES ({len(report.duplicates)})")
        lines.append("-" * 40)
        if report.duplicates:
            for d in report.duplicates:
                lines.append(f"  IDs: {', '.join(d.diamond_ids)}")
                lines.append(f"     Similarity: {d.similarity:.2f}")
                lines.append(f"     Action: {d.suggested_action}")
                lines.append("")
        else:
            lines.append("  No duplicates detected ✅")
        
        # Stale
        lines.append(f"\n🧓 STALE ENTRIES ({len(report.stale)})")
        lines.append("-" * 40)
        if report.stale:
            for s in report.stale:
                lines.append(f"  [{s.diamond_id}] - {s.age_days} days old")
        else:
            lines.append("  No stale entries ✅")
        
        # Clusters
        lines.append(f"\n🕸️ CLUSTERS ({len(report.clusters)})")
        lines.append("-" * 40)
        for cluster in report.clusters:
            lines.append(f"  {cluster.name}: {len(cluster.diamond_ids)} Diamonds")
            lines.append(f"     Tags: {', '.join(cluster.dominant_tags) or 'none'}")
        
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


# Global instance
consistency_engine = ConsistencyEngine()


# CLI Entry Point
def run_consistency_check():
    """Run consistency analysis from command line."""
    engine = ConsistencyEngine()
    report = engine.analyze()
    print(engine.format_report(report))
    return report


if __name__ == "__main__":
    run_consistency_check()
