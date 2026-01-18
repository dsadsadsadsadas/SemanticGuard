"""
ShadowGrid Database Models

SQLAlchemy models for player history, sessions, cases, and detection events.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, JSON, Enum as SQLEnum
)
from sqlalchemy.orm import DeclarativeBase, relationship
from enum import Enum


class Base(DeclarativeBase):
    """SQLAlchemy base class."""
    pass


class PlayerStatus(str, Enum):
    """Player account status."""
    ACTIVE = "active"
    WARNED = "warned"
    SHADOW_BANNED = "shadow_banned"
    TEMP_BANNED = "temp_banned"
    PERM_BANNED = "perm_banned"


class Player(Base):
    """
    Player model with historical statistics for Tier 2 detection.
    
    Stores aggregate stats across all sessions for history-based analysis.
    """
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Account status
    status = Column(SQLEnum(PlayerStatus), default=PlayerStatus.ACTIVE)
    ban_expires = Column(DateTime, nullable=True)
    
    # Aggregate statistics (for Tier 2 history features)
    total_sessions = Column(Integer, default=0)
    total_playtime_seconds = Column(Float, default=0.0)
    total_moves = Column(Integer, default=0)
    total_crystals = Column(Integer, default=0)
    total_deaths = Column(Integer, default=0)
    
    # Detection history
    total_flags = Column(Integer, default=0)
    total_bans = Column(Integer, default=0)
    avg_tier1_score = Column(Float, default=0.0)
    avg_tier2_score = Column(Float, default=0.0)
    max_detection_score = Column(Float, default=0.0)
    
    # Behavioral statistics
    avg_speed = Column(Float, default=0.0)
    avg_input_frequency = Column(Float, default=0.0)
    speed_violation_count = Column(Integer, default=0)
    fog_violation_count = Column(Integer, default=0)
    
    # Trust score (higher = more trusted)
    trust_score = Column(Float, default=0.5)
    
    # Relationships
    sessions = relationship("Session", back_populates="player")
    cases = relationship("Case", back_populates="player")
    
    def to_history_dict(self) -> dict:
        """Convert to Tier 2 history feature dict."""
        return {
            'total_sessions': self.total_sessions,
            'total_playtime': self.total_playtime_seconds,
            'avg_session_length': self.total_playtime_seconds / max(self.total_sessions, 1),
            'total_flags': self.total_flags,
            'total_bans': self.total_bans,
            'avg_tier1_score': self.avg_tier1_score,
            'avg_tier2_score': self.avg_tier2_score,
            'max_detection_score': self.max_detection_score,
            'avg_speed': self.avg_speed,
            'speed_violations': self.speed_violation_count,
            'fog_violations': self.fog_violation_count,
            'trust_score': self.trust_score,
            'account_age_days': (datetime.utcnow() - self.created_at).days,
            'days_since_last_play': (datetime.utcnow() - self.last_seen).days,
            'crystals_per_session': self.total_crystals / max(self.total_sessions, 1),
            'deaths_per_session': self.total_deaths / max(self.total_sessions, 1)
        }


class Session(Base):
    """
    Game session model.
    
    Stores per-session statistics and detection results.
    """
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    player_id = Column(String(64), ForeignKey("players.player_id"), nullable=False)
    
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    
    # Session stats
    crystals_collected = Column(Integer, default=0)
    deaths = Column(Integer, default=0)
    total_moves = Column(Integer, default=0)
    score = Column(Integer, default=0)
    
    # Detection results
    tier1_score = Column(Float, default=0.0)
    tier2_score = Column(Float, default=0.0)
    combined_score = Column(Float, default=0.0)
    was_flagged = Column(Boolean, default=False)
    verdict = Column(String(32), nullable=True)  # CLEAR, MONITOR, REVIEW, BAN
    
    # Feature snapshot (JSON blob)
    features = Column(JSON, nullable=True)
    
    # Movement data for replay
    replay_data = Column(JSON, nullable=True)
    
    # Relationships
    player = relationship("Player", back_populates="sessions")
    detection_events = relationship("DetectionEvent", back_populates="session")


class CaseStatus(str, Enum):
    """Case review status."""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    CLEARED = "cleared"
    BANNED = "banned"
    MONITORING = "monitoring"
    ESCALATED = "escalated"


class CasePriority(str, Enum):
    """Case priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Case(Base):
    """
    Tier 3 review case model.
    
    Tracks cases sent for human review.
    """
    __tablename__ = "cases"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(64), unique=True, nullable=False, index=True)
    player_id = Column(String(64), ForeignKey("players.player_id"), nullable=False)
    session_id = Column(String(64), ForeignKey("sessions.session_id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Case details
    status = Column(SQLEnum(CaseStatus), default=CaseStatus.PENDING)
    priority = Column(SQLEnum(CasePriority), default=CasePriority.MEDIUM)
    
    # Detection scores
    tier1_score = Column(Float, default=0.0)
    tier2_score = Column(Float, default=0.0)
    ai_verdict = Column(String(32), nullable=True)
    ai_confidence = Column(Float, default=0.0)
    
    # AI reasoning (from TabNet attention + Llama analysis)
    ai_reasoning = Column(Text, nullable=True)
    suspicious_features = Column(JSON, nullable=True)
    
    # Human review
    reviewer_id = Column(String(64), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    human_verdict = Column(String(32), nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    
    # Relationships
    player = relationship("Player", back_populates="cases")


class DetectionEvent(Base):
    """
    Individual detection event.
    
    Logs each time detection was triggered.
    """
    __tablename__ = "detection_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("sessions.session_id"), nullable=False)
    
    timestamp = Column(DateTime, default=datetime.utcnow)
    tick = Column(Integer, default=0)
    
    # Detection details
    tier = Column(Integer, default=1)  # 1, 2, or 3
    score = Column(Float, default=0.0)
    threshold = Column(Float, default=0.0)
    triggered = Column(Boolean, default=False)
    
    # Reason
    detection_type = Column(String(32), nullable=True)  # speedhack, wallhack, etc.
    reason = Column(Text, nullable=True)
    
    # Feature values at detection time
    feature_snapshot = Column(JSON, nullable=True)
    
    # Relationships
    session = relationship("Session", back_populates="detection_events")


class Match(Base):
    """
    Match model - groups all player cases from a single game.
    
    Used for:
    - Match history browsing in dashboard
    - Batch AI analysis at game end
    - RL training feedback loop
    """
    __tablename__ = "matches"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(64), unique=True, nullable=False, index=True)
    
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    
    # Match stats
    player_count = Column(Integer, default=0)
    cheater_count = Column(Integer, default=0)  # Ground truth count
    
    # AI Performance
    correct_detections = Column(Integer, default=0)
    incorrect_detections = Column(Integer, default=0)
    detection_accuracy = Column(Float, default=0.0)
    
    # RL Training
    rl_reward_total = Column(Float, default=0.0)
    rl_trained = Column(Boolean, default=False)
    
    # Relationships
    match_cases = relationship("MatchCase", back_populates="match", cascade="all, delete-orphan")


class MatchCase(Base):
    """
    Individual player case within a match.
    
    Tracks AI verdict vs ground truth for RL training.
    """
    __tablename__ = "match_cases"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String(64), ForeignKey("matches.match_id"), nullable=False)
    player_id = Column(String(64), nullable=False, index=True)
    
    # Ground truth (from demo/admin)
    is_cheater = Column(Boolean, default=False)
    cheat_type = Column(String(32), nullable=True)  # speedhack, etc.
    
    # AI Analysis
    ai_score = Column(Float, default=0.0)
    ai_verdict = Column(Boolean, default=False)  # True = detected as cheater
    ai_confidence = Column(Float, default=0.0)
    ai_reasoning = Column(Text, nullable=True)
    
    # Correctness
    was_correct = Column(Boolean, default=False)  # ai_verdict == is_cheater
    
    # RL Reward
    rl_reward = Column(Float, default=0.0)  # +1 correct, -1 incorrect
    
    # Session data snapshot
    total_moves = Column(Integer, default=0)
    features_snapshot = Column(JSON, nullable=True)
    
    # Relationships
    match = relationship("Match", back_populates="match_cases")

