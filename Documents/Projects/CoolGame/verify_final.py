
import asyncio
import sys
import os

# Add parent directory to path to import shadowgrid
sys.path.append(os.getcwd())

from shadowgrid.database import db_manager, MatchRepository

async def verify():
    repo = MatchRepository()
    matches = await repo.get_matches(limit=1)
    if not matches:
        print("❌ No matches found in database.")
        return

    match = matches[0]
    print(f"Match ID: {match.match_id}")
    print(f"Accuracy: {match.detection_accuracy * 100:.1f}%")
    print("-" * 30)
    
    for case in match.cases:
        correct = "✅" if case.is_correct else "❌"
        print(f"{case.player_id}: {case.ai_verdict} (Score: {case.ai_score:.1f}%) {correct}")

if __name__ == "__main__":
    asyncio.run(verify())
