"""Quick test: Connect a bot and check the API at the same time"""
import asyncio
import websockets
import json
import aiohttp

async def test():
    print("1. Connecting bot to ws://127.0.0.1:8000/ws/APITestBot ...")
    try:
        ws = await websockets.connect("ws://127.0.0.1:8000/ws/APITestBot", ping_interval=None)
        print("   Bot connected!")
        
        # Send one move to ensure we're fully connected
        await ws.send(json.dumps({'type': 'INPUT', 'direction': 'UP', 'tick': 123}))
        print("   Sent message, waiting...")
        await asyncio.sleep(1)
        
        print("2. Checking /players API...")
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:8000/players") as resp:
                data = await resp.json()
                print(f"   API Response: {data}")
        
        print("3. Checking /game/state API...")
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:8000/game/state") as resp:
                data = await resp.json()
                player_count = len(data.get('players', {}))
                print(f"   Players in game state: {player_count}")
                if 'players' in data:
                    print(f"   Player IDs: {list(data['players'].keys())}")
        
        await ws.close()
        print("4. Done!")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test())
