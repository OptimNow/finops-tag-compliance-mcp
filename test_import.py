import sys
import traceback

try:
    import mcp_server.utils.loop_detection
    print("Module imported successfully")
    print("Module contents:", dir(mcp_server.utils.loop_detection))
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
