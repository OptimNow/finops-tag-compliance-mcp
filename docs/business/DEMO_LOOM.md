# Demo Script — LinkedIn Video (< 60s)

> **Loom recording**: [https://www.loom.com/share/dba94ecd6ed44aa9b83d3e6a29b18d1d](https://www.loom.com/share/dba94ecd6ed44aa9b83d3e6a29b18d1d)

> **ICP**: Head of Cloud / VP Infrastructure
> **Format**: LinkedIn native video, < 60 seconds
> **Positioning**: Tool-as-Leverage — the agent is not the product, it's the accelerator
> **Core value angle**: *"This lets me say something uncomfortable, faster, with proof, without carrying the blame alone."*

---

## Strategic Context

This demo does NOT sell a tool. It demonstrates a capability that:

1. **Reduces political risk** — the data speaks, not you
2. **Accelerates decision-making** — from question to action plan in 2 prompts
3. **Provides proof** — auditable, shareable, structured output

The viewer should think: *"I need this before my next budget review."*

---

## Post Title

**63% of my cloud spend is unattributed. I fix that in 45 seconds.**

---

## Script

### HOOK — 0:00 to 0:08

| Visual | Voiceover |
|--------|-----------|
| Text overlay on dark background: **"63% of my cloud budget can't be attributed to anyone."** | *"If I can't attribute a cost to a team, I can't optimise it, I can't justify it. And when finance asks for answers, I'm the one who can't explain the spend."* |

**Purpose**: Emotional hook. The viewer recognizes themselves in the situation. This is about political exposure, not dashboards.

---

### STEP 1 — The Diagnostic — 0:08 to 0:25

| Visual | Voiceover |
|--------|-----------|
| Screen: Claude Desktop chat interface. User types the prompt below. Agent responds with real data. | *"One question. In return: 21% compliance, 107 violations, $45 of unattributed spend out of $71. Not another dashboard. A straight answer, with the data behind it."* |

**Prompt shown on screen:**

```
What's my current tag compliance and cost attribution gap?
```

**What the agent actually does (not shown to viewer):**
- Calls `check_tag_compliance` (resource_types: all)
- Calls `get_cost_attribution_gap`
- Synthesizes results in natural language

**Key numbers to highlight in the response:**

| Metric | Value |
|--------|-------|
| Compliance score | **21%** |
| Total violations | **107** across 41 resources |
| Cost attribution gap | **63%** ($45 of $71 unattributed) |
| Top missing tags | Environment, Owner, Application |
| Worst offenders | S3 buckets (49 violations), Lambda functions (27 violations) |

**Filming tip**: Let the response render for 2-3 seconds. The viewer needs to see real data, not a blur. Zoom on the key numbers if needed.

---

### STEP 2 — The Action — 0:25 to 0:45

| Visual | Voiceover |
|--------|-----------|
| Same chat. User types the second prompt. Agent produces a structured remediation plan + a Cloud Custodian policy. | *"One more sentence, and I have a prioritised action plan and an auto-remediation script ready to deploy. This isn't just a report. It's a plan I can act on straight away."* |

**Prompt shown on screen:**

```
Generate a remediation plan I can share with my team, and a Cloud Custodian policy to auto-tag the top violators.
```

**What the agent actually does:**
- Calls `generate_compliance_report` (format: markdown, include_recommendations: true)
- Generates a Cloud Custodian policy based on violation data (Claude's native generation)

**Expected output structure (show briefly on screen):**

```markdown
## Remediation Plan — Priority Order

### P0 — Critical (immediate)
- 16 S3 buckets missing all 3 required tags
- 9 Lambda functions with zero tags
  → Owner: platform-team@company.com
  → Action: Apply via Cloud Custodian policy below

### P1 — High (this sprint)
- 4 EC2 instances with invalid Environment values ("dev" → "development", "prod" → "production")
  → Action: Value correction, no new tags needed

### P2 — Medium (this quarter)
- Bedrock resources (4) — new service, tagging policy not yet enforced
  → Action: Add to onboarding checklist
```

```yaml
# Cloud Custodian — Auto-tag untagged S3 buckets
policies:
  - name: tag-untagged-s3-buckets
    resource: s3
    filters:
      - "tag:Environment": absent
    actions:
      - type: tag
        tags:
          Environment: development
          Owner: platform-team@company.com
          Application: unassigned
```

**Filming tip**: Don't try to show the full output. Scroll slowly for 3-4 seconds so the viewer sees structure (headers, priorities, YAML). The point is: *"This is actionable, not just informational."*

---

### CLOSE — 0:45 to 0:55

| Visual | Voiceover |
|--------|-----------|
| Text overlay: **"From visibility to action. In 2 questions."** | *"The problem with FinOps isn't visibility. It's acting on it. Having the data ready before you're asked for it."* |

---

## LinkedIn Post Copy

```
Tagging is not a technical problem.
It's the foundation of all cost attribution.

No tags → no attribution → no optimization → no governance.

63% of my cloud budget was invisible.
In 2 questions to a FinOps agent:
→ Full diagnostic (21% compliance, 107 violations)
→ Prioritized action plan + Cloud Custodian script ready to deploy

This isn't another dashboard.
It's a plan you can act on immediately.

#FinOps #CloudGovernance #AWS #CostOptimization #CloudCustodian
```

---

## Production Checklist

### Before Recording

- [ ] Claude Desktop open with `tagging-mcp-prod` connected
- [ ] Test both prompts — verify agent calls the right tools
- [ ] Verify numbers are current (re-run compliance check)
- [ ] Clean chat history (start fresh conversation)
- [ ] Screen resolution: 1920x1080, font size readable at mobile scale
- [ ] Dark mode ON (better for LinkedIn native video)

### Recording Setup

| Setting | Value |
|---------|-------|
| Tool filmed | Claude Desktop with MCP tagging-mcp |
| Screen capture | OBS or native (1080p minimum) |
| Audio | Voiceover recorded separately (quiet room) |
| Subtitles | **Mandatory** — 80% of LinkedIn video is watched on mute |
| Duration target | 50-55 seconds |
| Tone | Calm, direct, executive. No buzzwords. No "revolutionize". |

### What the Script Does NOT Do (Intentionally)

| Omission | Reason |
|----------|--------|
| No pricing mentioned | The tool is not the product — it's the lever for paid engagements |
| No technical deep-dive | Audience is Head of Cloud, not DevOps |
| No competitor comparison | Implicit before/after is stronger than "better than X" |
| No MCP/protocol jargon | Viewer sees "a chat that gives actionable results" |
| No "sign up" CTA | Implicit CTA: viewer DMs or comments asking "how do I get this?" |

---

## Underlying Data Reference

*Real data from production environment as of 2026-02-10:*

| Metric | Value | Source Tool |
|--------|-------|-------------|
| Compliance score | 21.2% | `check_tag_compliance` |
| Total resources scanned | 52 | `check_tag_compliance` |
| Non-compliant resources | 41 | `check_tag_compliance` |
| Total violations | 107 | `check_tag_compliance` |
| Regions scanned | 18 | `check_tag_compliance` |
| S3 bucket violations | 49 | `check_tag_compliance` |
| Lambda violations | 27 | `check_tag_compliance` |
| Invalid Environment values | 4 ("dev"/"prod" instead of "development"/"production") | `check_tag_compliance` |
| Required tags | Environment, Owner, Application | `get_tagging_policy` |
| Cost attribution gap | ~63% | `get_cost_attribution_gap` |

---

## Adaptation Notes

### For Different ICP (VP Engineering)

Shift the emotional hook from "budget attribution" to "engineering velocity":
- *"Every hour my team spends manually tagging resources is an hour they don't ship features."*
- Emphasize the Cloud Custodian automation (Step 2) over the compliance report.

### For Different ICP (CFO / Finance)

Shift from "tagging" to "cost allocation":
- *"$45 out of $71 in cloud spend can't be traced to any team or project. That's not a cloud problem. That's a financial controls problem."*
- Emphasize the cost attribution gap number and the ability to track improvement over time (`get_violation_history`).
