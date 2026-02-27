# System diagrams

This directory contains system diagrams for the FinOps Tag Compliance MCP Server, organized by format.

## Folder structure

```
docs/diagrams/
├── mermaid/     # Text-based diagrams (render on GitHub, version-friendly)
└── drawio/      # Visual diagrams (open with draw.io / diagrams.net)
```

---

## Mermaid diagrams

Mermaid diagrams render automatically on GitHub and can be edited in any text editor. View them in the [Mermaid Live Editor](https://mermaid.live/) or VS Code with the "Markdown Preview Mermaid Support" extension.

### [01 - System architecture](./mermaid/01-system-architecture.md)
**High-level overview of the entire system**

Shows all major components and their relationships: FastMCP stdio entry point, ServiceContainer, 14 tools, services, clients, and external integrations (AWS, Redis, SQLite). Includes multi-region scanning architecture and data flow patterns.

**Use this when**: You need to understand the overall system structure or explain the architecture to contributors.

---

### [02 - State machine diagrams](./mermaid/02-state-machine-diagrams.md)
**State transitions and lifecycle management**

Contains 4 state machines:
1. **Tool invocation lifecycle** — Complete request-to-response flow via stdio
2. **Resource compliance status** — Compliance state transitions
3. **Cache state machine** — Cache lookup and storage lifecycle
4. **Budget tracking** — Session budget enforcement

**Use this when**: You need to understand workflows, state transitions, or debug issues with tool invocations.

---

### [03 - Sequence diagrams](./mermaid/03-sequence-diagrams.md)
**Time-based interaction flows**

Contains 5 detailed sequences:
1. **Full compliance check** — End-to-end multi-region compliance scanning workflow
2. **Tag suggestion** — Pattern-based tag recommendation flow
3. **Cost attribution gap** — Cost analysis workflow
4. **Violation history** — Historical trend analysis
5. **Error handling and retry** — Error recovery patterns

**Use this when**: You need to understand how components interact over time or trace a specific workflow.

---

### [04 - Component diagram](./mermaid/04-component-diagram.md)
**Logical components and their dependencies**

Shows component hierarchy and layering, dependency matrix, component interfaces (ServiceContainer, services, clients), communication patterns, and testing strategy.

**Use this when**: Planning code changes, understanding dependencies, or documenting the software architecture.

---

## draw.io diagrams

Visual diagrams created with [draw.io / diagrams.net](https://app.diagrams.net/). Open `.drawio` files directly at [app.diagrams.net](https://app.diagrams.net/) or with the VS Code draw.io extension.

### [Local development setup](./drawio/local-dev-setup.drawio)
**Developer laptop environment and connections**

Shows the local development topology: MCP client options (Claude Desktop, Kiro IDE, VS Code/Cursor, MCP Inspector), the Python MCP server process with its internal layers, local config files and SQLite databases, and connections to AWS cloud services.

**Use this when**: Setting up a development environment, onboarding new contributors, or explaining how credentials flow.

---

### [MCP tool request flow](./drawio/mcp-tool-flow.drawio)
**Swimlane walkthrough of a single tool request**

Traces a `check_tag_compliance` request end-to-end across five swimlanes: User + Claude, MCP Protocol, Services, AWS APIs, and Cache/DB. Shows middleware pipeline, multi-region scanning, and response formatting.

**Use this when**: You want a visual, presentation-ready view of the tool request lifecycle. (See also: [Mermaid sequence diagram #1](./mermaid/03-sequence-diagrams.md) for the text-based equivalent.)

---

## Quick navigation

### By use case

| I want to... | Use this diagram |
|--------------|------------------|
| **Understand the overall system** | [System architecture](./mermaid/01-system-architecture.md) |
| **Set up my dev environment** | [Local dev setup](./drawio/local-dev-setup.drawio) |
| **Debug a workflow issue** | [Sequence diagrams](./mermaid/03-sequence-diagrams.md) |
| **Understand state transitions** | [State machine diagrams](./mermaid/02-state-machine-diagrams.md) |
| **Plan a code change** | [Component diagram](./mermaid/04-component-diagram.md) |
| **Present the tool flow** | [MCP tool request flow](./drawio/mcp-tool-flow.drawio) |

### By audience

| Audience | Recommended diagrams |
|----------|---------------------|
| **New contributors** | Local dev setup → System architecture → Component diagram |
| **Users** | System architecture |
| **Developers extending the server** | Component diagram, Sequence diagrams, State machines |
| **Presentations / demos** | draw.io diagrams (local dev setup, tool flow) |

## Related documentation

- [User manual](../USER_MANUAL.md) — How to use the MCP tools with Claude
- [Tagging policy guide](../TAGGING_POLICY_GUIDE.md) — Policy configuration reference
- [Tool logic reference](../TOOL_LOGIC_REFERENCE.md) — Detailed logic for each tool
- [IAM permissions](../security/IAM_PERMISSIONS.md) — Required AWS permissions
