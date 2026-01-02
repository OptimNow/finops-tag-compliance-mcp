import sys
import traceback

# Monkey-patch to catch exceptions during import
original_exec = exec

def traced_exec(code, *args, **kwargs):
    try:
        return original_exec(code, *args, **kwargs)
    except Exception as e:
        print(f"Exception during exec: {e}")
        traceback.print_exc()
        raise

# Try to load the file directly
with open("mcp_server/utils/loop_detection.py", "r") as f:
    code = f.read()

try:
    # Create a namespace
    namespace = {}
    exec(code, namespace)
    print("Code executed successfully")
    print("Namespace keys:", [k for k in namespace.keys() if not k.startswith('_')])
except Exception as e:
    print(f"Error executing code: {e}")
    traceback.print_exc()
