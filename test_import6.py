with open('mcp_server/utils/loop_detection.py') as f:
    content = f.read()

print(f'File size: {len(content)} bytes')
print(f'Lines: {len(content.splitlines())}')
print(f'Has LoopDetector: {"class LoopDetector" in content}')
print(f'Has LoopDetectedError: {"class LoopDetectedError" in content}')

# Check if there are any syntax errors
import ast
try:
    ast.parse(content)
    print("✓ File parses successfully")
except SyntaxError as e:
    print(f"✗ Syntax error: {e}")
    print(f"  Line {e.lineno}: {e.text}")
