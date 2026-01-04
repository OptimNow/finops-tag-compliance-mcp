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
