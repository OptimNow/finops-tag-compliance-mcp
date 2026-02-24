# System diagrams

This directory contains comprehensive system diagrams for the FinOps Tag Compliance MCP Server.

## Diagram index

### 📚 [00 - Diagram Best Practices](./00-diagram-best-practices.md)
**Essential reading for understanding and creating system diagrams**

Learn about:
- When to use different diagram types
- Best practices for each diagram type
- Common anti-patterns to avoid
- Recommended tools and resources

Start here if you're new to system diagrams or want to understand diagram selection.

---

### 🏗️ [01 - System Architecture](./01-system-architecture.md)
**High-level overview of the entire system**

Shows:
- All major components and their relationships
- API Gateway, MCP Protocol, Business Logic, Integration, and Data layers
- External integrations (AWS services, Redis, SQLite, CloudWatch)
- Data flow patterns
- Component dependencies

**Use this when**: You need to understand the overall system structure or explain the architecture to stakeholders.

---

### 🔄 [02 - State Machine Diagrams](./02-state-machine-diagrams.md)
**State transitions and lifecycle management**

Contains 4 state machines:
1. **Tool Invocation Lifecycle** - Complete request-to-response flow
2. **Resource Compliance Status** - Compliance state transitions
3. **Cache State Machine** - Cache lookup and storage lifecycle
4. **Budget Tracking** - Session budget enforcement

**Use this when**: You need to understand workflows, state transitions, or debug issues with tool invocations.

---

### 📊 [03 - Sequence Diagrams](./03-sequence-diagrams.md)
**Time-based interaction flows**

Contains 5 detailed sequences:
1. **Full Compliance Check** - End-to-end compliance scanning workflow
2. **Tag Suggestion** - AI-powered tag recommendation flow
3. **Cost Attribution Gap** - Cost analysis workflow
4. **Violation History** - Historical trend analysis
5. **Error Handling and Retry** - Error recovery patterns

**Use this when**: You need to understand how components interact over time or trace a specific workflow.

---

### 🧩 [04 - Component Diagram](./04-component-diagram.md)
**Logical components and their dependencies**

Shows:
- Component hierarchy and layering
- Dependency matrix
- Component interfaces
- Communication patterns
- Deployment units
- Testing strategy

**Use this when**: Planning code changes, understanding dependencies, or documenting the software architecture.

---

### 🚀 [05 - Deployment Architecture](./05-deployment-architecture.md)
**Physical deployment and infrastructure**

Contains 5 deployment options:
1. **Docker Compose** - Local development setup
2. **AWS EC2** - Production deployment with high availability
3. **Google Cloud Run** - Serverless auto-scaling deployment
4. **Kubernetes** - Enterprise-grade orchestration
5. **Security Architecture** - Security layers and controls

**Use this when**: Planning infrastructure, setting up environments, or discussing deployment options.

---

## Quick navigation

### By use case

| I want to... | Use this diagram |
|--------------|------------------|
| **Understand the overall system** | [System Architecture](./01-system-architecture.md) |
| **Debug a workflow issue** | [Sequence Diagrams](./03-sequence-diagrams.md) |
| **Understand state transitions** | [State Machine Diagrams](./02-state-machine-diagrams.md) |
| **Plan a code change** | [Component Diagram](./04-component-diagram.md) |
| **Set up infrastructure** | [Deployment Architecture](./05-deployment-architecture.md) |
| **Learn about diagrams** | [Diagram Best Practices](./00-diagram-best-practices.md) |

### By audience

| Audience | Recommended Diagrams |
|----------|---------------------|
| **Executives/Stakeholders** | System Architecture, Deployment Architecture |
| **Software Developers** | Component Diagram, Sequence Diagrams, State Machines |
| **DevOps Engineers** | Deployment Architecture, System Architecture |
| **New Team Members** | System Architecture → Component Diagram → Sequence Diagrams |
| **Security Reviewers** | Deployment Architecture (Security section), Sequence Diagrams |

### By complexity

| Level | Diagrams |
|-------|----------|
| **Beginner** | System Architecture, Deployment Architecture |
| **Intermediate** | Component Diagram, State Machine Diagrams |
| **Advanced** | Sequence Diagrams, Diagram Best Practices |

## Diagram technologies

All diagrams use [Mermaid](https://mermaid.js.org/) syntax, which:
- ✅ Can be viewed directly on GitHub
- ✅ Is version-controlled as text
- ✅ Can be edited in any text editor
- ✅ Can be rendered in most markdown viewers
- ✅ Can be embedded in documentation

### Viewing diagrams

1. **On GitHub**: Diagrams render automatically in markdown files
2. **VS Code**: Install the "Markdown Preview Mermaid Support" extension
3. **Online**: Use [Mermaid Live Editor](https://mermaid.live/)
4. **CLI**: Use `mmdc` (mermaid-cli) to generate images

## Contributing

When updating or adding diagrams:

1. **Follow the standards** in [Diagram Best Practices](./00-diagram-best-practices.md)
2. **Use Mermaid syntax** for consistency
3. **Update this README** if adding new diagrams
4. **Include context** - explain what the diagram shows and when to use it
5. **Test rendering** on GitHub before committing
6. **Add date/version** information in the document

## Related documentation

- [Architecture Overview](../architecture/) - Written architecture documentation
- [API Documentation](../api/) - API reference and specifications
- [Deployment Guide](../deployment/) - Detailed deployment instructions
- [Development Guide](../development/) - Developer setup and guidelines

## Diagram statistics

- **Total Diagrams**: 20+ Mermaid diagrams
- **Coverage**:
  - 1 System Architecture
  - 4 State Machines
  - 5 Sequence Diagrams
  - 6 Component/Dependency Diagrams
  - 5 Deployment Options
- **Format**: Mermaid markdown
- **Last Updated**: 2026-01-10

## Feedback

If you have suggestions for improving these diagrams or need additional diagrams:

1. Open an issue in the repository
2. Provide context on what you're trying to understand
3. Suggest what diagram type would help

Good diagrams are essential for system understanding - we appreciate your feedback!
