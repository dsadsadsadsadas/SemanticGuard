import asyncio
import os
from sqlalchemy import select
from shadowgrid.database import db_manager, Session, Player

async def check_db():
    print("🔎 Checking ShadowGrid Database...")
    print(f"DB Path: {os.path.abspath('shadowgrid.db')}")
    
    async with db_manager.session_factory() as db:
        # Check Players
        result = await db.execute(select(Player))
        players = result.scalars().all()
        print(f"\n👤 Players Found: {len(players)}")
        for p in players:
            print(f"  - {p.player_id} (Status: {p.status})")
            print(f"    Stats: {p.total_sessions} sessions, {p.total_deaths} deaths, {p.total_crystals} crystals")
            print(f"    Detection: Flags={p.total_flags}, Bans={p.total_bans}, Trust={p.trust_score:.2f}")

        # Check Sessions
        result = await db.execute(select(Session).order_by(Session.started_at.desc()).limit(5))
        sessions = result.scalars().all()
        print(f"\n🎮 Recent Sessions ({len(sessions)}):")
        for s in sessions:
            duration = f"{s.duration_seconds:.1f}s" if s.duration_seconds else "Active/Crashed"
            print(f"  - {s.session_id} ({s.player_id})")
            print(f"    Time: {s.started_at} | Duration: {duration}")
            print(f"    Score: {s.score} | Crystals: {s.crystals_collected} | Deaths: {s.deaths}")
            if s.was_flagged:
                print(f"    ⚠️ FLAGGED (Score: {s.combined_score:.2f})")

if __name__ == "__main__":
    if not os.path.exists("shadowgrid.db"):
        print("❌ No database found! Run the server first.")
    else:
        asyncio.run(check_db())
