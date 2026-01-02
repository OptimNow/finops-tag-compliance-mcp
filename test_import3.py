import sys
import traceback

# Add detailed exception handling
sys.excepthook = lambda type, value, tb: traceback.print_exception(type, value, tb)

try:
    # Import step by step
    print("Importing hashlib...")
    import hashlib
    print("OK")
    
    print("Importing json...")
    import json
    print("OK")
    
    print("Importing logging...")
    import logging
    print("OK")
    
    print("Importing datetime...")
    from datetime import datetime, timedelta
    print("OK")
    
    print("Importing RedisCache...")
    from mcp_server.clients.cache import RedisCache
    print("OK")
    
    print("Importing get_correlation_id...")
    from mcp_server.utils.correlation import get_correlation_id
    print("OK")
    
    print("Now trying to import loop_detection module...")
    import mcp_server.utils.loop_detection as ld
    print("Module imported")
    print("Module attributes:", [x for x in dir(ld) if not x.startswith('_')])
    
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
