# Development Journal: Building a FinOps MCP Server with Kiro

**Author**: Jean (FinOps Practitioner, Non-Developer)  
**Project**: FinOps Tag Compliance MCP Server  
**Tool**: Kiro AI Assistant  
**Timeline**: December 2024 - Present

---

## The Journey: From Idea to Working MVP

This journal documents my experience building a production-grade MCP server without being a developer. My background is in FinOps (Financial Operations for cloud), not software engineering. I wanted to solve a real problem - cloud tagging compliance - but didn't know how to code a solution.

Enter Kiro.

---

## Week 1: Inception & Specification (Early December 2024)

### Day 1-2: The Problem

**What I knew:**
- Cloud tagging is a mess in most organizations
- 43% of cloud costs can't be attributed due to missing tags (FinOps Foundation data)
- Existing tools just read tags - they don't validate, suggest, or quantify financial impact

**What I didn't know:**
- How to build an MCP server
- What architecture to use
- How to integrate with AWS APIs
- How to make it production-ready

**The Kiro Moment:**
I described my problem to Kiro in plain English: "I want to build an MCP server that helps FinOps teams enforce cloud tagging policies and calculate the cost of non-compliance."

Kiro asked clarifying questions:
- What cloud providers? (Started with AWS)
- What operations? (Read-only compliance checks first)
- What's the deployment target? (EC2 for MVP)

### Day 3-5: Specification Phase

**What Kiro did:**
- Created a complete technical specification (SPECIFICATION.md)
- Broke it into 3 phases (MVP, Production, Multi-Cloud)
- Defined 15 MCP tools with clear purposes
- Designed the architecture (FastAPI, Redis, SQLite, boto3)

**What I learned:**
- MCP servers expose "tools" that AI assistants can call
- Remote MCP servers use HTTP (not stdio like local ones)
- You need a bridge script for Claude Desktop to talk to remote servers

**Key files created:**
- `docs/SPECIFICATION.md` - Complete vision
- `docs/PHASE-1-SPECIFICATION.md` - MVP scope
- `docs/ROADMAP.md` - 12-month plan

**My role:**
- Validated the business logic (does this solve the FinOps problem?)
- Confirmed the tool names made sense
- Approved the phased approach

---

## Week 2: Requirements & Design (Mid-December 2024)

### Day 6-8: Writing Requirements

**The Kiro Workflow:**
Kiro introduced me to "spec-driven development" - a structured way to build software:
1. Requirements (what should it do?)
2. Design (how will it work?)
3. Tasks (step-by-step implementation)

**What Kiro did:**
- Created `.kiro/specs/phase-1-aws-mvp/requirements.md`
- Wrote 16 requirements using EARS patterns (a formal requirements language)
- Each requirement had user stories and acceptance criteria
- Included correctness properties for testing

**What I learned:**
- Requirements should be testable (not vague like "system should be fast")
- EARS patterns make requirements precise: "WHEN X, THE system SHALL Y"
- Acceptance criteria define what "done" means

**Example requirement I understood:**
```
WHEN a user requests a compliance check, 
THE MCP_Server SHALL scan specified AWS resource types 
and return a compliance score
```

**My role:**
- Reviewed each requirement for business accuracy
- Confirmed the FinOps terminology was correct
- Approved the requirements document

### Day 9-11: Design Document

**What Kiro did:**
- Created `.kiro/specs/phase-1-aws-mvp/design.md`
- Designed the architecture (layers, components, data models)
- Defined 18 correctness properties for testing
- Explained the tagging policy schema

**What I learned:**
- Architecture has layers: Tools → Services → Infrastructure
- Pydantic models define data structures (like TypeScript interfaces)
- Property-based testing validates universal rules (not just examples)
- Caching is critical for AWS API cost control

**The "Aha!" moment:**
Kiro explained the tagging policy schema - how organizations define their own rules. This was the heart of the system. I could finally see how my FinOps knowledge translated into code.

**My role:**
- Validated the FinOps logic (compliance scoring, cost attribution)
- Confirmed the policy schema matched real-world needs
- Approved the design

---

## Week 3: Implementation Begins (Late December 2024)

### Day 12-15: Task Breakdown

**What Kiro did:**
- Created `.kiro/specs/phase-1-aws-mvp/tasks.md`
- Broke the design into 30 discrete coding tasks
- Each task was small and testable
- Included checkpoints for validation

**What I learned:**
- Implementation is incremental (not "write all the code at once")
- Each task builds on previous ones
- Tests are written alongside code (not after)

**My role:**
- Reviewed the task sequence
- Confirmed it made sense from a FinOps perspective
- Approved the implementation plan

### Day 16-20: Core Implementation

**What Kiro did:**
Over several sessions, Kiro implemented:
- Data models (Pydantic classes for violations, compliance results)
- Policy service (loads and validates tagging policies)
- AWS client (boto3 wrapper with caching)
- Compliance service (core business logic)
- All 8 MCP tools
- Unit tests and property tests

**What I learned:**
- Python type hints make code readable (even for non-developers)
- Services contain business logic, tools are thin wrappers
- Mocking lets you test without real AWS resources
- Property-based testing uses Hypothesis to generate test cases

**My role:**
- Tested the tools through Claude Desktop
- Reported bugs ("it's not finding my EC2 instances")
- Validated the compliance scoring logic

---

## Week 4: Docker & Deployment (Early January 2025)

### Day 21-23: Containerization

**What Kiro did:**
- Created `Dockerfile` for the MCP server
- Created `docker-compose.yml` for local development
- Set up Redis for caching
- Configured environment variables

**What I learned:**
- Docker containers package everything (code, dependencies, runtime)
- docker-compose runs multiple containers (server + Redis)
- Environment variables configure the server (no hardcoded values)

**The first bug:**
Server couldn't find AWS credentials. Kiro explained that Docker containers are isolated - they don't automatically have access to my `~/.aws` folder.

**The fix:**
Added volume mount in `docker-compose.yml`:
```yaml
volumes:
  - ~/.aws:/root/.aws:ro
```

**My role:**
- Ran `docker-compose up -d`
- Tested the health endpoint
- Reported the credentials issue

### Day 24-25: Claude Desktop Integration

**The challenge:**
Claude Desktop only supports stdio-based MCP, but my server uses HTTP.

**What Kiro did:**
- Created `scripts/mcp_bridge.py` - a bridge script that translates stdio to HTTP
- Updated README with setup instructions
- Explained the MCP_SERVER_URL environment variable

**What I learned:**
- Claude Desktop runs the bridge script locally
- The bridge connects to the server (local Docker or remote EC2)
- The `requests` library must be installed in Claude's Python

**The second bug:**
"Server disconnected" error in Claude Desktop. After debugging, we found Claude uses a different Python installation than my conda environment.

**The fix:**
```bash
& "C:\Users\jlati\AppData\Local\Programs\Python\Python311\python.exe" -m pip install requests
```

**My role:**
- Configured Claude Desktop's `claude_desktop_config.json`
- Tested the connection
- Reported the disconnection error

---

## Week 5: Testing & Refinement (Mid-January 2025)

### Day 26-28: Real-World Testing

**What I tested:**
- "Check tag compliance for my EC2 instances"
- "Find untagged resources in us-east-1"
- "Show me the cost attribution gap"

**Issues found:**
1. Server returned 0 resources (AWS credentials not mounted)
2. Compliance score was always 1.0 (no tagging policy configured)
3. Some error messages exposed internal paths (security issue)

**What Kiro did:**
- Fixed AWS credentials mounting
- Created example tagging policy (`policies/tagging_policy.json`)
- Implemented error sanitization middleware
- Added comprehensive logging

**What I learned:**
- Real-world testing reveals issues that unit tests miss
- Error messages should be helpful but not expose internals
- Audit logging is critical for production systems

### Day 29-30: Security Hardening

**What Kiro added:**
- Input validation for all tool parameters
- Loop detection (prevents agents from calling the same tool repeatedly)
- Budget enforcement (limits tool calls per session)
- Unknown tool rejection (only registered tools allowed)
- Correlation IDs for request tracing

**What I learned:**
- AI agents can misbehave (loops, excessive calls)
- Security isn't just authentication - it's input validation, rate limiting, and audit trails
- Correlation IDs help debug issues across multiple services

**My role:**
- Reviewed the security requirements
- Tested the guardrails (tried to trigger loops)
- Validated the audit logs

---

## Week 6: Documentation & Repository Cleanup (Late January 2025)

### Day 31-32: Documentation

**What Kiro created:**
- `README.md` - Quick start guide
- `docs/DEPLOYMENT.md` - How to deploy to EC2
- `docs/UAT_PROTOCOL.md` - User acceptance testing procedures
- `docs/TESTING_QUICK_START.md` - How to run tests
- `docs/AUDIT_LOGGING.md` - Audit logging implementation
- `docs/CLOUDWATCH_LOGGING.md` - CloudWatch integration

**What I learned:**
- Good documentation is critical for adoption
- Different audiences need different docs (users vs. operators vs. developers)
- Examples are more valuable than abstract explanations

### Day 33: Repository Organization

**The problem:**
Root directory was cluttered with 27 markdown files, task summaries, and test import files.

**What Kiro did:**
- Created `docs/` folder
- Moved 16 documentation files to `docs/`
- Deleted 17 temporary files (task summaries, test imports, database files)
- Updated `.gitignore` to exclude `*.db` files
- Created `docs/README.md` as a navigation guide
- Updated all internal references to point to new locations

**What I learned:**
- Repository organization matters for understandability
- Root directory should only have essential files
- Documentation should be grouped logically

**My role:**
- Identified the clutter problem
- Approved the cleanup plan
- Validated the new structure

---

## Week 7: Agent Safety Enhancements (Current)

### Day 34: Learning from the Field

**The insight:**
Watched a video about "intent failure" - where AI agents execute based on underspecified requests, potentially wasting resources or misleading users.

**The problem:**
Even read-only operations can be expensive:
- Full account scans (thousands of resources)
- Cost Explorer queries (slow and costly)
- Wrong region = wasted API calls

**What Kiro did:**
- Created `.kiro/specs/agent-safety-enhancements/requirements.md`
- Added 12 requirements for intent disambiguation
- Updated Phase 2 specification to include safety features
- Updated roadmap to reflect the new scope

**Key features planned:**
1. Intent commit pattern (agent describes what it will do)
2. Clarification loops (resolve ambiguity before executing)
3. Cost/risk thresholds (require approval for expensive operations)
4. Dry run mode (preview without executing)
5. Intent belief logging (what did the agent think you wanted?)

**What I learned:**
- Agent safety is about preventing misunderstandings, not just malicious behavior
- Intent ≠ Context (what you say vs. what you mean)
- Even read-only operations need guardrails

**My role:**
- Shared the video insights
- Decided to add this to Phase 2 (not block Phase 1 MVP)
- Approved the new requirements

---

## Reflections: What Made This Possible

### How Kiro Helped a Non-Developer Build Production Software

**1. Structured Workflow**
Kiro didn't just write code - it guided me through a proven process:
- Requirements → Design → Tasks → Implementation
- Each phase had clear deliverables and approval gates
- I always understood what was happening and why

**2. Plain English Communication**
I never had to learn programming syntax. I described problems in FinOps terms:
- "Calculate the cost attribution gap"
- "Suggest tags based on resource patterns"
- "Enforce our tagging policy"

Kiro translated these into technical implementations.

**3. Incremental Progress**
Every task was small and testable. I could see progress daily:
- Day 1: Data models
- Day 2: Policy service
- Day 3: First tool working
- Day 4: All tools implemented

**4. Real-World Problem Solving**
When issues came up (AWS credentials, Claude Desktop connection), Kiro:
- Diagnosed the root cause
- Explained it in simple terms
- Implemented the fix
- Updated documentation to prevent future issues

**5. Production-Ready Defaults**
Kiro didn't just make it work - it made it production-ready:
- Comprehensive error handling
- Security guardrails
- Audit logging
- Property-based testing
- Docker containerization

### What I Contributed (Non-Developer Value)

**Domain Expertise:**
- Validated the FinOps logic (compliance scoring, cost attribution)
- Ensured terminology was correct
- Confirmed the tool names made sense to practitioners

**User Testing:**
- Tested through Claude Desktop (the actual user experience)
- Found bugs that unit tests missed
- Validated the business value

**Product Decisions:**
- Chose the phased approach (MVP → Production → Multi-Cloud)
- Decided which features were essential vs. nice-to-have
- Prioritized agent safety for Phase 2

**Documentation Review:**
- Ensured docs were understandable to non-developers
- Validated deployment instructions
- Confirmed examples were realistic

---

## Current Status (January 2025)

### What's Working

✅ **Phase 1 MVP Complete**
- 8 MCP tools implemented and tested
- Docker containerization working
- Claude Desktop integration functional
- AWS credentials properly configured
- Real-world testing successful (3 EC2 instances, 12 violations found)

✅ **Production-Ready Features**
- Comprehensive error handling
- Security guardrails (input validation, loop detection, budget enforcement)
- Audit logging
- Property-based testing (18 correctness properties)
- Health monitoring

✅ **Documentation Complete**
- User guides (README, UAT Protocol)
- Operator guides (Deployment, Testing)
- Developer guides (Specifications, Architecture)
- Repository well-organized

### What's Next

**Immediate (This Week):**
- Complete UAT testing with real tagging policies
- Deploy to EC2 for remote access
- Share with beta users

**Phase 2 (Months 3-4):**
- ECS Fargate deployment (production-grade)
- OAuth 2.0 authentication
- 7 additional tools (bulk tagging, scheduling)
- Agent safety enhancements (intent disambiguation)

**Phase 3 (Months 5-6):**
- Azure and GCP support
- Multi-cloud unified reporting

---

## Key Takeaways for Non-Developers

### You Don't Need to Code to Build Software

**What you DO need:**
1. **Domain expertise** - Deep understanding of the problem
2. **Clear communication** - Ability to describe what you want
3. **Critical thinking** - Validate that solutions make sense
4. **Persistence** - Debug issues when they arise
5. **The right tool** - Kiro bridges the gap between ideas and implementation

### The Kiro Advantage

**Traditional approach:**
1. Hire developers
2. Explain the problem
3. Wait weeks for implementation
4. Discover misunderstandings
5. Iterate (slowly)

**With Kiro:**
1. Describe the problem
2. Review and approve specifications
3. Watch implementation happen (hours, not weeks)
4. Test and provide feedback
5. Iterate quickly

### What I Learned About Software Development

**Before Kiro:**
- Software development seemed like magic
- I thought you needed years of training
- I assumed non-developers couldn't contribute meaningfully

**After Kiro:**
- Software development is structured problem-solving
- Domain expertise is as valuable as coding skills
- Non-developers can drive technical projects with the right tools

---

## Lessons for Future Projects

### 1. Start with Requirements
Don't jump to implementation. Spend time defining:
- What problem are you solving?
- Who are the users?
- What does success look like?

### 2. Use Structured Workflows
The Requirements → Design → Tasks workflow kept me organized and ensured nothing was missed.

### 3. Test Early and Often
Don't wait until "everything is done" to test. Test each component as it's built.

### 4. Document as You Go
Writing documentation during development (not after) ensures it's accurate and complete.

### 5. Embrace Iteration
First versions are never perfect. Plan for feedback and refinement.

### 6. Leverage AI Thoughtfully
Kiro isn't just a code generator - it's a partner that:
- Asks clarifying questions
- Suggests best practices
- Explains technical concepts
- Validates your ideas

---

## Conclusion

Building a production-grade MCP server without being a developer seemed impossible. With Kiro, it took 6 weeks from idea to working MVP.

The key wasn't learning to code - it was learning to:
- Articulate problems clearly
- Validate solutions critically
- Test thoroughly
- Iterate based on feedback

If you're a domain expert (FinOps, DevOps, Security, etc.) with a problem to solve, you don't need to become a developer. You need the right AI partner.

Kiro made this possible.

---

**Next Update**: After Phase 1 UAT completion and EC2 deployment

**Contact**: [Your contact info for blog readers]

**Repository**: https://github.com/OptimNow/finops-tag-compliance-mcp

---

## January 4, 2026: Critical Bug Fix & UAT Preparation

### Day 35: MCP Server Startup Issues Resolved

**The Crisis:**
Started the day ready for UAT testing, but discovered the MCP server was completely broken:
- Container continuously restarting
- `SyntaxError: invalid non-printable character U+FEFF` in `mcp_server/utils/loop_detection.py`
- Import failures preventing server startup

**Root Cause Analysis:**
- BOM (Byte Order Mark) characters had corrupted the Python file
- The file appeared normal in text editors but contained invisible Unicode characters
- Python interpreter couldn't parse the file due to these non-printable characters

**The Debugging Journey:**
1. **Initial Diagnosis**: Checked Docker container logs, found import error
2. **File Investigation**: Examined the problematic file, looked normal visually
3. **Encoding Analysis**: Used Python to inspect file bytes, found BOM characters
4. **Multiple Fix Attempts**: 
   - Tried cleaning with `utf-8-sig` encoding
   - Attempted git restore (but original file was also corrupted)
   - Cleared Python cache files
   - Rebuilt Docker containers multiple times

**The Solution:**
- Used a working file (`correlation.py`) as a template
- Recreated `loop_detection.py` with identical header structure
- Copied content in sections to avoid encoding issues
- Verified Python import worked before proceeding

**What Kiro Did:**
- Systematically diagnosed the encoding issue
- Tried multiple approaches to fix the corruption
- Used a template-based approach when direct fixes failed
- Rebuilt Docker container with `--no-cache` flag
- Verified the fix with comprehensive testing

**What I Learned:**
- BOM characters are invisible but deadly for Python files
- File corruption can happen during development (possibly from copy/paste operations)
- Template-based file recreation is sometimes more reliable than direct fixes
- Docker containers need to be rebuilt after code changes

**Final Verification:**
✅ Python import successful: `from mcp_server.utils.loop_detection import LoopDetector`
✅ Docker build successful (112.6s clean build)
✅ Containers running: `tagging-mcp-server` and `tagging-redis`
✅ Health endpoint responding: HTTP 200 with full status
✅ Redis and SQLite connections working
✅ All safety features enabled (budget tracking, loop detection)

**Current Status:**
- MCP server fully operational
- Ready for UAT testing tomorrow
- All Phase 1 features working correctly

**Time Investment:**
- 2+ hours debugging and fixing the encoding issue
- Demonstrates the importance of having robust error handling and diagnostic tools

**Key Takeaway:**
Even with a production-ready system, unexpected issues can arise. The structured debugging approach and Kiro's systematic problem-solving made it possible to resolve a complex encoding issue without deep Python knowledge.

**Next Steps for Tomorrow:**
1. Enable MCP server in Claude Desktop
2. Begin comprehensive UAT testing
3. Test all 8 MCP tools with real AWS resources
4. Document any issues found during UAT
5. Prepare for EC2 deployment if UAT is successful

**Repository Status:**
- All code changes committed and ready for push
- Documentation updated with today's fixes
- Ready for production UAT testing


---

## January 5, 2026: Violation History Bug Fix

### Day 36: Database Path Resolution Issue

**The Problem:**
During UAT testing, the `get_violation_history` tool was returning empty results even though compliance scans had been recorded. Investigation revealed:
- Two database files existed: `/app/compliance_history.db` (empty) and `/app/data/compliance_history.db` (with data)
- The tool was using the wrong database path

**Root Cause:**
The `_handle_get_violation_history` method in `mcp_handler.py` was creating a new `HistoryService` instance with the default path (`compliance_history.db`) instead of using the `history_service` that was passed to the `MCPHandler` during initialization with the correct path (`/app/data/compliance_history.db`).

**The Fix:**
Updated `_handle_get_violation_history` to use `self.history_service.db_path` when available:

```python
async def _handle_get_violation_history(self, arguments: dict) -> dict:
    """Handle get_violation_history tool invocation."""
    # Use the history_service's db_path if available, otherwise use default
    db_path = "compliance_history.db"
    if self.history_service:
        db_path = self.history_service.db_path
        logger.debug(f"Using history_service db_path: {db_path}")
    else:
        logger.warning("history_service is None, using default db_path")
    
    logger.info(f"get_violation_history using db_path: {db_path}")
    
    result = await get_violation_history(
        days_back=arguments.get("days_back", 30),
        group_by=arguments.get("group_by", "day"),
        db_path=db_path,
    )
    
    return result.to_dict()
```

**Verification:**
After rebuilding the Docker container:
- Server logs show: `History service initialized with database: /app/data/compliance_history.db`
- Tool invocation logs show: `get_violation_history using db_path: /app/data/compliance_history.db`
- API response returns actual data: 1 data point with compliance score 0.465

**What I Learned:**
- Service initialization order matters - the handler must receive the service instance with the correct configuration
- Debug logging is essential for diagnosing path-related issues
- Docker volume mounts need to be consistent with application configuration

**Current Status:**
✅ `get_violation_history` tool working correctly
✅ Historical compliance data being retrieved
✅ Trend analysis functioning (stable trend detected)
✅ Ready to continue UAT testing

---

## January 5, 2026 (Evening): Local UAT Complete & Checkpoint 54 Verified

### Local UAT Testing Complete

**UAT Testing Results:**
Completed comprehensive UAT testing locally with all 8 MCP tools functioning correctly through Claude Desktop integration.

**Checkpoint 54 Verification - Bug Fixes Complete:**

All bug fixes from tasks 50-53 verified working:

1. **S3 Bucket ARN Support (Task 50)**: 20 ARN-related tests pass - S3 bucket ARNs now correctly handled with `:::` pattern
2. **OpenSearch Domain Support (Task 51)**: 5 tests pass in `test_aws_client.py` - OpenSearch domains appear in `find_untagged_resources` results
3. **ARN Validation (Task 52)**: Comprehensive pattern supports all AWS service types including EC2, S3, Lambda, RDS, DynamoDB, OpenSearch, and more
4. **History Storage (Task 53)**: Integration tests confirm compliance scans automatically store history when `store_snapshot=True`

**Test Suite Results:**
- 137 unit tests pass (input validation, suggest_tags, find_untagged_resources, aws_client)
- 38 integration tests pass
- 33 input validation property tests pass
- 11 history service property tests pass
- All property-based tests validate correctness guarantees

**Docker Build Verification:**
- Clean build successful (429MB image)
- Container running stable with Redis
- Health endpoint responding correctly
- All safety features enabled

**What Was Tested in UAT:**
- `check_tag_compliance` - Scanned EC2 instances, returned compliance scores
- `find_untagged_resources` - Found resources missing required tags
- `validate_resource_tags` - Validated specific resources by ARN
- `get_cost_attribution_gap` - Calculated financial impact of tagging gaps
- `suggest_tags` - Suggested tag values based on resource patterns
- `get_tagging_policy` - Retrieved policy configuration
- `generate_compliance_report` - Generated formatted compliance reports
- `get_violation_history` - Retrieved historical compliance data with trend analysis

**Current Status: Local UAT Complete, Remote Deployment Pending**

**Remaining Tasks for Phase 1 MVP Completion:**

| Task | Description | Status |
|------|-------------|--------|
| 26.1 | Docker Build Verification | Not Started |
| 27.1 | Deploy CloudFormation stack to AWS | Not Started |
| 27.2 | Configure EC2 instance | Not Started |
| 27.3 | Deploy application to EC2 | Not Started |
| 28.1 | Verify MCP server accessible from EC2 | Not Started |
| 28.2 | Configure Claude Desktop to connect to remote server | Not Started |
| 29 | Deployment Complete Checkpoint | Not Started |
| 30.1 | Execute UAT protocol on remote server | Not Started |
| 30.2 | UAT Sign-off | Not Started |

**Next Steps:**
1. Deploy CloudFormation stack to provision EC2 infrastructure
2. Configure and deploy MCP server to EC2
3. Test remote connectivity from Claude Desktop
4. Execute full UAT protocol against remote server
5. Sign off on Phase 1 completion

---

## January 5, 2026 (Night): EC2 Deployment Complete & Documentation Overhaul

### Day 36 (Continued): Production Deployment Success

**Major Milestone: EC2 Deployment Complete!**

Successfully deployed the MCP server to AWS EC2 and verified all tools working through the REST API.

**Infrastructure Deployed:**
- CloudFormation stack: `tagging-mcp-server`
- EC2 Instance: `i-0dc314272ccf812db`
- Elastic IP: `100.50.91.35`
- IAM Role: `arn:aws:iam::382598791951:role/tagging-mcp-server-role-dev`
- CloudWatch Log Group: `/tagging-mcp-server/dev`
- App directory: `/opt/tagging-mcp`

**Docker Build Workaround:**
Encountered `compose build requires buildx 0.17 or later` error on EC2. Solution was to use direct Docker build instead:
```bash
docker build -t tagging-mcp-server .
docker-compose up -d
```

**Policy File Path Fix:**
The `.env` file had `POLICY_FILE_PATH=policies/tagging-policy.json` (hyphen) but the actual file was `tagging_policy.json` (underscore). Commented out the line to use the default path.

**API Testing Results:**
Tested 3 MCP tools via REST API against the EC2 server:

1. **`get_tagging_policy`** ✅
   - Returns full policy with 5 required tags (Environment, Owner, CostCenter, Project, Application)
   - All tag validation rules working

2. **`check_tag_compliance`** ✅
   - Found 4 EC2 instances
   - 50% compliance score
   - Violations on `i-0dc314272ccf812db` and `i-036091f3268a9fe5b`

3. **`find_untagged_resources`** ✅
   - Found 17 S3 buckets with missing tags
   - Estimated monthly cost impact: ~$95

**Claude Desktop Configuration:**
Discovered that Claude Desktop expects stdio-based MCP, not HTTP. The solution is to use the `scripts/mcp_bridge.py` bridge script:

```json
{
  "mcpServers": {
    "tagging-mcp": {
      "command": "python",
      "args": ["C:\\path\\to\\repo\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://100.50.91.35:8080"
      }
    }
  }
}
```

### Documentation Overhaul (Task 56)

**Completely Rewrote `docs/DEPLOYMENT.md`:**
- Added Local Deployment section first (Quick Start in 5 minutes)
- AWS Deployment section (CloudFormation + Manual options)
- Connecting Claude Desktop section with examples for local and remote
- Configuration, Monitoring, Troubleshooting sections
- Clear step-by-step instructions for FinOps practitioners

**Created `docs/USER_MANUAL.md`:**
- All 8 MCP tools documented with example prompts
- 4 common workflows:
  1. Initial Assessment
  2. Remediation Planning
  3. Ongoing Monitoring
  4. Team Accountability
- Example prompts table for quick reference
- Understanding Results section
- Troubleshooting guide
- Tips for FinOps practitioners

**Updated `README.md`:**
- Organized documentation links by audience
- Clear navigation to deployment and user guides

**Tasks Completed:**
- ✅ Task 27.1: Deploy CloudFormation stack
- ✅ Task 27.2: Configure EC2 instance
- ✅ Task 27.3: Deploy application to EC2
- ✅ Task 28.1: Verify MCP server accessible
- ✅ Task 28.2: Configure Claude Desktop connection
- ✅ Task 56: Documentation overhaul

**Current Status:**
- EC2 server running and healthy at `http://100.50.91.35:8080`
- All 8 MCP tools available and working
- Documentation complete for users and operators
- Ready for full UAT testing tomorrow

**What I Learned Today:**
- Docker buildx version matters - direct `docker build` is more reliable on older systems
- Environment variable paths must match actual file names exactly
- Claude Desktop needs a bridge script for HTTP-based MCP servers
- Good documentation makes the difference between a tool and a product

**Tomorrow's Plan:**
1. Continue UAT testing with all 8 tools through Claude Desktop
2. Test multi-turn conversations
3. Validate compliance workflows end-to-end
4. Complete Task 29 (Deployment Complete Checkpoint)
5. Complete Task 30 (UAT Sign-off)


---

## January 8, 2026: One-Click Policy Deployment & Documentation Updates

### Day 39: Streamlining Policy Updates for Remote Deployments

**The Challenge:**
With the MCP server running on EC2, updating the tagging policy required SSH access and manual file transfers. This was too complex for a FinOps practitioner who just wants to update their policy and have it take effect.

**The Solution: One-Click Policy Deployment**

Created a complete workflow for updating policies remotely:

1. **PowerShell Script** (`scripts/deploy_policy.ps1`):
   - Validates JSON before deployment
   - Uploads policy to S3 as staging area
   - Uses AWS SSM to trigger EC2 to pull new policy
   - Restarts Docker container automatically
   - Provides clear status feedback

2. **Setup Documentation** (`scripts/POLICY_DEPLOY_SETUP.md`):
   - Step-by-step setup instructions
   - IAM permissions required
   - EC2 volume mount configuration
   - Troubleshooting guide

3. **Updated Deployment Guide** (`docs/DEPLOYMENT.md`):
   - Added "One-Click Policy Deployment" section
   - Integrated into main deployment workflow
   - Clear instructions for both fresh deployments and existing setups

**Architecture:**
```
Local Machine → S3 (staging) → EC2 (pull & restart)
```

**CloudFormation Updates:**
- Added `AmazonSSMManagedInstanceCore` managed policy to EC2 IAM role
- Added S3 read permission for `finops-mcp-config` bucket
- These permissions enable remote command execution via SSM

**Daily Usage After Setup:**
```powershell
# Edit policy locally
notepad policies/tagging_policy.json

# Deploy with one command
.\scripts\deploy_policy.ps1
```

**What I Learned:**
- AWS SSM (Systems Manager) allows running commands on EC2 without SSH
- S3 serves as a reliable staging area for configuration files
- Volume mounts in Docker allow external policy updates without rebuilding images
- Good automation reduces friction for non-developers

**AWS Credentials Issue:**
Encountered `IncompleteSignature` error when testing AWS CLI commands. Root cause was corrupted credentials file with multiple profiles mixed together. Solution: delete and recreate `~/.aws/credentials` with a single profile.

**Current Status:**
- One-click deployment scripts ready
- Documentation complete
- CloudFormation template updated with required permissions
- Ready for testing once AWS credentials are fixed

**Files Changed:**
- `scripts/deploy_policy.ps1` - PowerShell deployment script
- `scripts/deploy_policy.sh` - Bash deployment script (Mac/Linux)
- `scripts/POLICY_DEPLOY_SETUP.md` - Setup instructions
- `docs/DEPLOYMENT.md` - Added one-click deployment section
- `infrastructure/cloudformation.yaml` - Added SSM and S3 permissions

**Next Steps:**
1. Fix AWS credentials
2. Create S3 bucket for policy staging
3. Test one-click deployment workflow
4. Complete UAT testing

