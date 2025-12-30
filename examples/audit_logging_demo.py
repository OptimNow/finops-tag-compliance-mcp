"""
Demonstration of the audit logging system.

This script shows how to use the audit middleware and query audit logs.
"""

import asyncio
import tempfile
import os
from mcp_server.middleware import audit_tool
from mcp_server.services import AuditService
from mcp_server.models import AuditStatus


# Example tool with audit logging
@audit_tool
async def example_compliance_check(resource_types: list[str], severity: str = "all") -> dict:
    """Example tool that checks compliance."""
    print(f"Checking compliance for {resource_types} with severity {severity}")
    return {
        "compliance_score": 0.85,
        "total_resources": 100,
        "violations": 15,
    }


@audit_tool
async def example_failing_tool(should_fail: bool = True) -> dict:
    """Example tool that can fail."""
    if should_fail:
        raise ValueError("This tool failed intentionally for demo purposes")
    return {"status": "success"}


async def main():
    """Run the audit logging demonstration."""
    # Use a temporary database for this demo
    temp_db = tempfile.mktemp(suffix=".db")
    
    # Monkey patch AuditService to use temp db
    original_init = AuditService.__init__
    
    def patched_init(self, db_path=None):
        original_init(self, db_path=temp_db)
    
    AuditService.__init__ = patched_init
    
    try:
        print("=" * 60)
        print("Audit Logging Demonstration")
        print("=" * 60)
        print()
        
        # 1. Call some tools
        print("1. Calling example tools...")
        print("-" * 60)
        
        result1 = await example_compliance_check(
            resource_types=["ec2:instance", "rds:db"],
            severity="errors_only"
        )
        print(f"✅ Compliance check result: {result1}")
        print()
        
        result2 = await example_compliance_check(
            resource_types=["s3:bucket"],
            severity="all"
        )
        print(f"✅ Compliance check result: {result2}")
        print()
        
        # Try a failing tool
        try:
            await example_failing_tool(should_fail=True)
        except ValueError as e:
            print(f"❌ Tool failed as expected: {e}")
        print()
        
        # 2. Query audit logs
        print("2. Querying audit logs...")
        print("-" * 60)
        
        audit_service = AuditService()
        all_logs = audit_service.get_logs()
        
        print(f"Total invocations logged: {len(all_logs)}")
        print()
        
        # 3. Show all logs
        print("3. All audit log entries:")
        print("-" * 60)
        for log in all_logs:
            status_icon = "✅" if log.status == AuditStatus.SUCCESS else "❌"
            print(f"{status_icon} {log.tool_name}")
            print(f"   Timestamp: {log.timestamp}")
            print(f"   Status: {log.status.value}")
            print(f"   Execution time: {log.execution_time_ms:.2f}ms")
            if log.error_message:
                print(f"   Error: {log.error_message}")
            print()
        
        # 4. Filter by status
        print("4. Failed invocations only:")
        print("-" * 60)
        failures = audit_service.get_logs(status=AuditStatus.FAILURE)
        print(f"Found {len(failures)} failed invocation(s)")
        for log in failures:
            print(f"❌ {log.tool_name}: {log.error_message}")
        print()
        
        # 5. Filter by tool name
        print("5. Compliance check invocations only:")
        print("-" * 60)
        compliance_logs = audit_service.get_logs(tool_name="example_compliance_check")
        print(f"Found {len(compliance_logs)} compliance check invocation(s)")
        for log in compliance_logs:
            print(f"✅ {log.tool_name} - {log.execution_time_ms:.2f}ms")
        print()
        
        # 6. Calculate statistics
        print("6. Statistics:")
        print("-" * 60)
        total = len(all_logs)
        successful = sum(1 for log in all_logs if log.status == AuditStatus.SUCCESS)
        failed = total - successful
        success_rate = (successful / total * 100) if total > 0 else 0
        
        print(f"Total invocations: {total}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Success rate: {success_rate:.1f}%")
        print()
        
        avg_time = sum(log.execution_time_ms or 0 for log in all_logs) / total if total > 0 else 0
        print(f"Average execution time: {avg_time:.2f}ms")
        print()
        
        print("=" * 60)
        print("Demo complete!")
        print("=" * 60)
        
    finally:
        # Cleanup
        AuditService.__init__ = original_init
        if os.path.exists(temp_db):
            os.unlink(temp_db)


if __name__ == "__main__":
    asyncio.run(main())
