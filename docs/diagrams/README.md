# System diagrams

This directory contains system diagrams for the FinOps Tag Compliance MCP Server, showing the stdio/local architecture used when running with Claude Desktop or MCP Inspector.

## Diagram index

### 🏗️ [01 - System architecture](./01-system-architecture.md)
**High-level overview of the entire system**

Shows:
- All major components and their relationships
- FastMCP stdio entry point, ServiceContainer, tools, services, and clients
- External integrations (AWS services, Redis, SQLite)
- Multi-region scanning architecture
- Data flow patterns

**Use this when**: You need to understand the overall system structure or explain the architecture to contributors.

---

### 🔄 [02 - State machine diagrams](./02-state-machine-diagrams.md)
**State transitions and lifecycle management**

Contains 4 state machines:
1. **Tool invocation lifecycle** — Complete request-to-response flow via stdio
2. **Resource compliance status** — Compliance state transitions
3. **Cache state machine** — Cache lookup and storage lifecycle
4. **Budget tracking** — Session budget enforcement

**Use this when**: You need to understand workflows, state transitions, or debug issues with tool invocations.

---

### 📊 [03 - Sequence diagrams](./03-sequence-diagrams.md)
**Time-based interaction flows**

Contains 5 detailed sequences:
1. **Full compliance check** — End-to-end multi-region compliance scanning workflow
2. **Tag suggestion** — Pattern-based tag recommendation flow
3. **Cost attribution gap** — Cost analysis workflow
4. **Violation history** — Historical trend analysis
5. **Error handling and retry** — Error recovery patterns

**Use this when**: You need to understand how components interact over time or trace a specific workflow.

---

### 🧩 [04 - Component diagram](./04-component-diagram.md)
**Logical components and their dependencies**

Shows:
- Component hierarchy and layering
- Dependency matrix
- Component interfaces (ServiceContainer, services, clients)
- Communication patterns
- Testing strategy

**Use this when**: Planning code changes, understanding dependencies, or documenting the software architecture.

---

## Quick navigation

### By use case

| I want to... | Use this diagram |
|--------------|------------------|
| **Understand the overall system** | [System architecture](./01-system-architecture.md) |
| **Debug a workflow issue** | [Sequence diagrams](./03-sequence-diagrams.md) |
| **Understand state transitions** | [State machine diagrams](./02-state-machine-diagrams.md) |
| **Plan a code change** | [Component diagram](./04-component-diagram.md) |

### By audience

| Audience | Recommended diagrams |
|----------|---------------------|
| **Contributors** | System architecture → Component diagram → Sequence diagrams |
| **Users** | System architecture |
| **Developers extending the server** | Component diagram, Sequence diagrams, State machines |

## Diagram technologies

All diagrams use [Mermaid](https://mermaid.js.org/) syntax, which:
- ✅ Renders automatically on GitHub
- ✅ Is version-controlled as text
- ✅ Can be edited in any text editor
- ✅ Can be viewed in VS Code with the "Markdown Preview Mermaid Support" extension
- ✅ Can be rendered at [Mermaid Live Editor](https://mermaid.live/)

## Related documentation

- [User manual](../USER_MANUAL.md) — How to use the MCP tools with Claude
- [Tagging policy guide](../TAGGING_POLICY_GUIDE.md) — Policy configuration reference
- [Tool logic reference](../TOOL_LOGIC_REFERENCE.md) — Detailed logic for each tool
- [IAM permissions](../security/IAM_PERMISSIONS.md) — Required AWS permissions
