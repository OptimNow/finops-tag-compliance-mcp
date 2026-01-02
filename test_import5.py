import sys
import traceback

# Try to load the file directly with better error handling
with open("mcp_server/utils/loop_detection.py", "r") as f:
    lines = f.readlines()

# Find the imports
for i, line in enumerate(lines[:30], 1):
    print(f"{i:3d}: {line.rstrip()}")

print("\n\nNow trying to execute imports...")

try:
    import hashlib
    print("✓ hashlib")
    import json
    print("✓ json")
    import logging
    print("✓ logging")
    from typing import Optional
    print("✓ Optional")
    from datetime import datetime, timedelta
    print("✓ datetime, timedelta")
    
    print("\nTrying relative imports...")
    from mcp_server.clients.cache import RedisCache
    print("✓ RedisCache")
    from mcp_server.utils.correlation import get_correlation_id
    print("✓ get_correlation_id")
    
    print("\nAll imports successful!")
    
except Exception as e:
    print(f"✗ Error: {e}")
    traceback.print_exc()
