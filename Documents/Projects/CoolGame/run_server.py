"""Start ShadowGrid Server"""
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    print("🎮 Starting ShadowGrid Server (Production Mode)...")
    uvicorn.run(
        "shadowgrid.server.main:app",
        host="127.0.0.1",  # Explicit IPv4
        port=8000,
        reload=False,
        log_level="warning",  # Suppress HTTP spam
        access_log=False      # No per-request logs
    )
