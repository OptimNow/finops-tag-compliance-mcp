import sys
import traceback

try:
    # Try to import the module with detailed error reporting
    import importlib
    spec = importlib.util.spec_from_file_location(
        "loop_detection",
        "mcp_server/utils/loop_detection.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["loop_detection"] = module
    spec.loader.exec_module(module)
    print("Module loaded successfully")
    print("Module contents:", dir(module))
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
