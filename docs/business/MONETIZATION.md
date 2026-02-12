# FinOps Tag Compliance MCP - Go-to-Market Strategy

**Version**: 2.0
**Last Updated**: January 2025
**Status**: Execution Plan

---

## Executive Summary

Phase 1 MVP is complete. We've validated the tech internally. Now it's time to validate the business model.

**Strategy**: Start with self-hosted licensing (low complexity, high margins), then scale to AWS Marketplace and SaaS once we have paying customers and proven demand.

**Target**: 10 paying customers and €36-72K ARR within 6 months.

### Next 3 Months - Quick View

**Month 1 (January): Beta Testing**

Actions:
- Send simple confidentiality agreement (`docs/SIMPLE_CONFIDENTIALITY_AGREEMENT.md`) to 3-5 testers
- Grant GitHub access once signed
- Collect structured feedback

Deliverable: 3 test reports + product-market fit validation

**Month 2 (February): License System Implementation**

Actions:
- Set up Supabase license server (2 days)
- Add license validation to MCP server (3 days)
- Test with sample license keys

Deliverable: Functional license system

**Month 3 (March): First Paying Customers**

Actions:
- Create pricing page (Notion or simple HTML)
- Integrate Stripe (or bank transfer)
- Contact 20-30 prospects
- Target: 3-5 paying customers at €1,499-4,999/year

Deliverable: €5-15K revenue + validated business model

### Recommended Pricing

```
Starter: €1,499/year (€1,049 Early Adopter -30%)
- Max 1K AWS resources
- Email support (48h)
- Self-hosted

Professional: €4,999/year (€3,499 Early Adopter -30%)
- Max 10K AWS resources
- Email support (24h)
- Self-hosted

Enterprise: €9,999+/year (custom)
- Unlimited resources
- Slack support (4h SLA)
- Custom features
- Self-hosted
```

**Early Adopter Discount**: 30% lifetime discount for first 10 customers

---

## 6-Month Strategic Roadmap

### Current Situation (January 2025)

**What's done**:
- Phase 1 MVP complete and functional
- 50+ AWS resource types supported
- MCP server deployable on EC2 (Docker)
- Complete documentation (technical + user)
- Internal testing validated
- Proprietary license in place

**Goal for next 6 months**: Transform the MVP into a viable business with our first 10 paying customers.

**Target Revenue**: €3K-6K MRR by June 2025 (€36-72K ARR)

---

### Phase 0: Beta Testing (January-February 2025)

**Goal**: Validate product-market fit with external users before launching commercially.

**What we're doing**:

Weeks 1-2 (Mid-January):
- Identify 5 potential testers (FinOps freelancers, AWS consultants, DevOps leads)
- Send outreach emails (template: `docs/BETA_TESTER_PITCH_EN.md`)
- Get simple gentleman's agreement on confidentiality via email confirmation (template: `docs/SIMPLE_CONFIDENTIALITY_AGREEMENT.md`)
- Mention potential resell/co-sell partnerships for freelancers and consultants

Weeks 3-4 (End of January):
- Grant GitHub access to signed testers (read-only collaborators)
- Send access emails with deployment instructions
- Week 1 check-in: verify successful deployment

Weeks 5-8 (February):
- Provide responsive support (24-48h response time)
- Week 3 check-in: progress review with each tester
- Collect test reports (template in `docs/UAT_PROTOCOL.md`)
- Analyze feedback: critical bugs, improvement suggestions, validated use cases

**Deliverables**:
- 3-5 completed test reports
- 2-3 case studies with quantified metrics (e.g., "reduced audit time from 2 days to 30 minutes")
- List of 5-10 priority bugs to fix
- Value proposition validation (utility score ≥7/10)

**Investment**:
- Time: 10-15h/week (tester support + bug fixes)
- Cost: €0 (free for testers, no additional expenses)

**Go/No-Go Decision Criteria**:
- 80%+ of testers rate utility ≥7/10
- No unresolved critical bugs
- At least 2 use cases with quantified value (time or money saved)
- 50%+ of testers interested in commercial version

---

### Phase 1: First Paying Customers (March-April 2025)

**Goal**: Get 3-5 paying customers, validate pricing and business model, generate €1.5-3K MRR.

**What we're doing**:

Weeks 9-10 (Early March):
- Fix critical bugs identified in Phase 0
- Implement license system (see `docs/LICENSE_SYSTEM_IMPLEMENTATION.md`):
  - Set up Supabase for license validation (free tier)
  - Add license validation to MCP server
  - Test with sample license keys
- Create simple pricing page (Notion or basic HTML)
- Set up Stripe payment (or bank transfer for larger deals)

Weeks 11-12 (Mid-March):
- Prepare "Early Adopter" offer: 30% lifetime discount for first 10 customers
- Contact 20-30 prospects:
  - LinkedIn: search "FinOps" + "DevOps" + "Cloud Architect"
  - Communities: FinOps Foundation, AWS User Groups
  - Personal network: former colleagues, freelancers
- Offer beta testers 50% lifetime discount to convert to paying customers

Weeks 13-16 (Late March - April):
- Follow up with prospects: email at Day 3, Day 7, Day 14
- Offer personalized demos (30 min calls)
- Convert trials to paid: check-in at Day 7, Day 15, Day 25
- Provide responsive customer support (<24h email response)
- Document objections and responses (build sales playbook)

**Pricing** (Self-Hosted License):

```
Starter: €1,499/year
- Up to 1,000 AWS resources
- Email support (48h response)
- Annual license
- Customer deploys on their AWS

Professional: €4,999/year
- Up to 10,000 AWS resources
- Priority email support (24h response)
- Annual license
- Customer deploys on their AWS

Enterprise: Custom pricing (€9,999+/year)
- Unlimited resources
- Slack support (4h SLA)
- Custom features
- Customer deploys on their AWS
```

**Early Adopter Offer**: 30% lifetime discount for first 10 customers
- Starter: €1,049/year (instead of €1,499)
- Professional: €3,499/year (instead of €4,999)

**Deliverables**:
- License system functional and tested
- Pricing page live with Stripe integration
- 3-5 signed paying customers
- €1.5-3K MRR confirmed
- Sales playbook documented

**Investment**:
- Time: 20-30h/week (sales + customer support)
- Cost:
  - License server (Supabase): €0 (free tier)
  - Docker image hosting (S3): ~€5/month
  - Stripe fees: 1.5% + €0.25 per transaction
  - Marketing: €0-500 (optional LinkedIn ads)

---

### Phase 2: Scaling + AWS Marketplace (May-June 2025)

**Goal**: Double customer count (6-10 customers), launch on AWS Marketplace, reach €5-8K MRR.

**What we're doing**:

May 2025:
- Improve product with Phase 1 customer feedback
- Create detailed case studies:
  - Customer A: "Reduced unattributed costs from 43% to 5%"
  - Customer B: "Saves 15 hours/month on tagging compliance"
- Prepare AWS Marketplace:
  - Register for AWS Seller Central (free, 2-3 weeks approval)
  - Create product assets (logo PNG 110x110 and 300x300)
  - Write product description (500-2000 words)
  - Define EULA (End User License Agreement)
  - Set pricing (same tiers as self-hosted)

June 2025:
- Launch AWS Marketplace listing
- Intensify prospecting: 50 new prospects contacted
- Attend 1-2 FinOps events/conferences
- Optimize conversion: A/B test landing page, reduce onboarding friction
- Consider Phase 2 technical (ECS Fargate): If MRR ≥€5K, invest in scalability using revenues

**AWS Marketplace Setup**:

Timeline:
- Weeks 1-2: Seller registration + asset preparation
- Week 3: Submit listing (draft)
- Weeks 4-5: AWS review (security, compliance)
- Week 6: Listing goes live

Pricing on AWS Marketplace:
- Same tiers as self-hosted
- AWS takes 3% commission (acceptable)
- Payment 30 days after month-end

**Deliverables**:
- 6-10 paying customers (including 2-3 via AWS Marketplace)
- €5-8K MRR
- 2-3 published case studies (website + LinkedIn)
- Live AWS Marketplace listing
- Decision on Phase 2 technical (ECS) or continue Phase 1 (EC2)

**Investment**:
- Time: 25-35h/week
- Cost:
  - AWS Marketplace: €0 registration, 3% commission on sales
  - Marketing: €500-1,000 (LinkedIn ads + events)
  - Infrastructure: €40-200/month depending on load

---

## Success Metrics (KPIs)

**Product Metrics**:
- Uptime: ≥99% (Phase 1), ≥99.5% (Phase 2)
- Response time: <2s for compliance checks
- Critical bugs open: 0
- Successful deployment rate: ≥80%

**Business Metrics**:
- MRR (Monthly Recurring Revenue):
  - End of February: €0 (free testing)
  - End of April: €1.5-3K
  - End of June: €5-8K
- Customer count:
  - End of April: 3-5
  - End of June: 6-10
- CAC (Customer Acquisition Cost): <€500 (Phase 1)
- LTV:CAC Ratio: ≥3:1 (LTV = 12-18 months of MRR)
- Monthly churn rate: <5%

**Marketing Metrics**:
- Landing page traffic: 200-500 visitors/month
- Free trial conversion: ≥10%
- Trial to paid conversion: ≥15-20%
- Customer testimonials: 3-5

---

## Revenue Projections (Conservative Scenario)

| Month | Customers | MRR | ARR Run-Rate |
|-------|-----------|-----|--------------|
| Feb 2025 | 0 (testing) | €0 | €0 |
| Mar 2025 | 2 | €1,000 | €12K |
| Apr 2025 | 4 | €2,500 | €30K |
| May 2025 | 6 | €4,500 | €54K |
| Jun 2025 | 8 | €6,500 | €78K |
| **6-month total** | - | **€14,500** | - |

**Cost Projections**:

| Category | Months 1-2 | Months 3-4 | Months 5-6 | 6-Month Total |
|----------|------------|------------|------------|---------------|
| AWS Infrastructure | €40 | €80 | €150 | €270 |
| Stripe fees (1.5%+0.25) | €0 | €50 | €100 | €150 |
| Marketing | €0 | €200 | €500 | €700 |
| SaaS tools | €50 | €50 | €50 | €150 |
| **Total** | **€90** | **€380** | **€800** | **€1,270** |

**Profitability**:

| Period | Revenue | Costs | Profit | Margin |
|--------|---------|-------|--------|--------|
| Months 1-2 | €0 | €90 | -€90 | - |
| Months 3-4 | €3,500 | €380 | €3,120 | 89% |
| Months 5-6 | €11,000 | €800 | €10,200 | 93% |
| **6-month total** | **€14,500** | **€1,270** | **€13,230** | **91%** |

Note: These figures exclude founder time (bootstrapped approach). Goal is to prove the business model works before investing more.

---

## Monetization Options (Prioritized)

Now that we have our roadmap, here's how we'll monetize, in order of priority.

### Option 1: Self-Hosted License (Primary - Start Now)

**Why this first**: Lowest complexity, highest margins, no infrastructure costs, customers keep control of their data.

**How it works**:

You provide:
- Docker container with MCP server
- CloudFormation/Terraform for AWS deployment
- License key (validated against your license server)
- Complete documentation
- Email support

Customer:
- Deploys container on their AWS (EC2, ECS, or Lambda)
- Enters license key at startup
- Pays annual or monthly license fee

**License validation system**:

```python
# In your MCP server
import requests

def validate_license(license_key: str) -> dict:
    response = requests.post(
        "https://license.optimnow.io/validate",
        json={"key": license_key}
    )
    return response.json()  # {"valid": bool, "plan": str, "max_resources": int}

# At server startup
license_key = os.getenv("OPTIMNOW_LICENSE_KEY")
if not validate_license(license_key)["valid"]:
    raise Exception("Invalid license key. Contact jean@optimnow.io")
```

**Pricing tiers**:

```
Starter: €1,499/year (€1,049 Early Adopter)
- Up to 1,000 resources
- Email support (48h)
- Self-hosted deployment

Professional: €4,999/year (€3,499 Early Adopter)
- Up to 10,000 resources
- Priority support (24h)
- Self-hosted deployment

Enterprise: €9,999+/year (custom)
- Unlimited resources
- Slack support (4h SLA)
- Custom features
```

**Revenue projection (Year 1)**:
- Conservative: 8-10 customers = €30-50K ARR
- Aggressive: 15-20 customers = €60-100K ARR

**Pros**:
- Fast to implement (1-2 weeks)
- No infrastructure costs for you
- Customer keeps data control (easier security approval)
- 95%+ profit margins (pure software)
- No credential trust issues

**Cons**:
- Customer must know how to deploy (deployment friction)
- More complex support (different environments)
- Risk of license piracy (mitigated by validation server)

**Implementation guide**: See `docs/LICENSE_SYSTEM_IMPLEMENTATION.md`

---

### Option 2: AWS Marketplace (Secondary - Month 5-6)

**Why second**: Good distribution channel, but 2-3 months setup time. Better to have paying customers first to strengthen your listing.

**How it works**:

Customer journey:
1. Customer finds MCP in AWS Marketplace
2. Clicks "Subscribe" (no credit card if AWS account exists)
3. AWS redirects to your registration page
4. Customer deploys (self-hosted) or uses your hosted version
5. AWS bills customer monthly (consolidated with AWS bill)
6. AWS pays you (minus 3% fee) monthly

**Two models available**:

Model A: SaaS Subscription (hosted by you)
- You run the infrastructure
- Customer just configures and uses
- Higher price point (you manage everything)
- More complex for you to scale

Model B: Container Listing (self-hosted by customer)
- Customer deploys on their AWS
- You provide container + license
- Same as Option 1, but through AWS Marketplace
- Easier distribution, no hosting for you

**Recommended**: Start with Model B (container listing, self-hosted)

**Pricing**: Same tiers as Option 1, AWS takes 3% commission

**Revenue projection**: €50-100K ARR from Marketplace (6-12 months after launch)

**Timeline**:
- Week 1-2: AWS Seller Central registration (2-3 weeks approval)
- Week 3: Create listing (product description, logo, pricing)
- Week 4-5: AWS review (security, compliance)
- Week 6: Listing goes live

**Pros**:
- Built-in distribution channel
- Customer trust (AWS brand)
- Consolidated billing (easier for enterprises)
- Low acquisition cost per customer

**Cons**:
- 2-3 months to launch
- 3% marketplace fee
- AWS review process can be slow
- Less direct customer relationship

---

### Option 3: Cross-Account SaaS — Hosted Server + Client Read-Only Role (Primary SaaS Model)

**Why this model**: Combines the simplicity of hosted SaaS (no deployment for the customer) with the security of cross-account read-only access (no credentials to share). Inspired by the CloudZero connection model.

**How it works**:

You:
- Deploy MCP on your AWS account (ECS Fargate — Phase 2.5 infrastructure)
- Expose URL: https://mcp.optimnow.io
- Manage infrastructure, updates, security, scaling
- Use STS AssumeRole to read customer accounts (read-only)

Customer:
- Deploys a CloudFormation template in their account (~5 minutes, 1-click)
- Template creates an IAM Role with read-only permissions + External ID
- Provides the Role ARN to OptimNow → connection established
- No compute in their account, no credentials to share, no data leaves their account
- Revokes access by deleting the CloudFormation stack

**Architecture**:
```
┌─────────────────────────────────────────────────────────────────────────┐
│                    OPTIMNOW ACCOUNT (Control Plane)                      │
│                                                                         │
│  MCP Server (ECS Fargate) ─── STS AssumeRole ──► Client Account A      │
│                               (External ID)  ──► Client Account B      │
│  Redis (cache per client)                    ──► Client Account C      │
│  RDS (client registry + audit)               ──► Client Account N      │
│                                                                         │
│  Dashboard / Billing / Licensing                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

**Customer onboarding**:
1. Customer signs up on optimnow.io
2. Receives a unique External ID + CloudFormation 1-click URL
3. Deploys CloudFormation in their AWS Console (~5 min)
4. Provides Role ARN back to OptimNow
5. OptimNow verifies access (STS AssumeRole health check)
6. Customer starts scanning via Claude Desktop / MCP

**Customer setup** (Claude Desktop config):
```json
{
  "mcpServers": {
    "optimnow-finops": {
      "command": "python",
      "args": ["mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "https://mcp.optimnow.io",
        "API_KEY": "customer_api_key_xyz"
      }
    }
  }
}
```

**Security model** (strictly less intrusive than CloudZero):
- 100% read-only: ~20 IAM actions, zero write/delete
- External ID per customer: prevents confused deputy attacks
- No credentials exchanged: customer never shares access keys
- Customer-revocable: delete CloudFormation stack → instant revocation
- IAM policy published on GitHub: full transparency for security reviews
- No raw data stored: only compliance scores and aggregated metrics
- TLS everywhere: STS calls + API calls encrypted in transit

**Pricing** (SaaS, customer deploys nothing):

```
Starter: €149/month (€1,499/year)
- Up to 1,000 AWS resources
- 1 AWS account
- Email support (48h)

Professional: €399/month (€3,999/year)
- Up to 10,000 AWS resources
- Up to 5 AWS accounts
- Priority support (24h)
- Historical compliance trends

Enterprise: €999+/month (custom)
- Unlimited resources
- Unlimited AWS accounts
- Slack support (4h SLA)
- Custom tagging policy
- Dedicated onboarding
```

**Early Adopter Offer**: 30% lifetime discount for first 10 customers

**Revenue projection**: €80-150K ARR (Year 1-2)

**Pros**:
- Zero deployment friction for customers (1-click CloudFormation only)
- No credentials shared (cross-account IAM role, not access keys)
- You control updates, monitoring, and scaling
- Enterprise-friendly security model (read-only, auditable, revocable)
- Strictly less intrusive than CloudZero (less data stored)
- Customer data never leaves their account (only scores sent back)
- Compatible with AWS Marketplace (Option 2) for distribution

**Cons**:
- You pay infrastructure costs (~€150-200/month for ECS + RDS + Redis)
- Customer must deploy CloudFormation (minimal friction but not zero)
- Multi-tenant isolation must be rigorous (cache, audit, rate limiting)
- STS session management complexity

**When to launch**: After Phase 2.6 is complete (requires ECS Fargate + multi-tenant AssumeRole layer).

**CloudFormation template**: `infrastructure/cloudformation-client-readonly.yaml` (open-source, auditable)

---

### Option 3b: Self-Hosted SaaS (Legacy — Deprecated in favor of Option 3)

**Note**: This option (customer shares AWS credentials with a hosted server) is **deprecated** in favor of Option 3 (cross-account IAM role). The cross-account model is more secure and enterprise-friendly because the customer never shares credentials — they just create a read-only IAM role.

Kept here for reference only.

---

### Option 4: Enterprise Direct Sales (Ongoing - Month 6+)

**Why**: Large contracts, long-term relationships, high LTV. But long sales cycles (3-6 months).

**How it works**:

Typical deal:
- Base license: €50-150K/year depending on company size
- Professional services: €15-50K (implementation, training)
- Premium support: +€25K/year (24/7, Slack, <4h SLA)
- Custom features: €25-100K (one-time)

**Sales process**:

Month 1: Discovery
- Initial demo (30-60 min)
- Requirements gathering
- Stakeholder meetings
- Technical deep-dive

Month 2: Proof of Value (PoV)
- 30-day trial with real data
- Scan 10% of resources to start
- Generate compliance reports
- Show ROI (cost attribution gap closed)

Months 3-4: Negotiation
- Custom pricing based on scope
- Legal review
- Security review (SOC2, GDPR compliance)
- Procurement process

Months 5-6: Contract & Deployment
- Contract signed
- Professional services engagement
- Implementation (1-2 weeks)
- Training (1-2 days)
- Go-live

**Revenue projection**: €300-500K ARR from 3-5 enterprise customers (Year 2)

**Pros**:
- Highest margins (85-95%)
- Predictable annual revenue
- Long-term relationships
- Upsell opportunities (PS, training, custom features)
- Strong reference customers

**Cons**:
- Long sales cycles (3-6 months)
- Requires dedicated sales resources
- High upfront investment (demos, PoVs, security reviews)
- Customer concentration risk
- Must support enterprise requirements (SSO, compliance, SLAs)

---

### Options NOT Recommended (For Now)

**Open Core**: Too early. Risk of losing competitive advantage before validating business model. Consider in Year 2 if you want developer-led growth.

**Managed Service**: High operational overhead, doesn't scale well, requires hiring. Consider only if customers explicitly request it.

**Freemium**: Low conversion rates (5-10%), free users cost money. Better to focus on paying customers from day 1.

---

## Strategic Decisions

### Decision 1: Stay Proprietary (For Now)

**Current stance**: 100% proprietary code, self-hosted licenses.

**Why**: Too early to open source. Business model not validated yet. Competitive advantage (MCP + FinOps) is unique.

**When to reconsider**: If you have 20+ paying customers, €10-15K MRR stable, and want to accelerate adoption with Open Core model.

**Open Core option (future)**: Open source Phase 1 (AWS-only, 8 tools), keep proprietary multi-cloud (Azure, GCP) and enterprise features (SSO, multi-tenancy).

---

### Decision 2: Bootstrap (Don't Raise Funds)

**Current stance**: Self-funded, no outside capital.

**Why**:
- Low capital requirements (infrastructure €40-200/month)
- Excellent margins (90%+)
- Keep 100% control and equity
- No investor pressure to scale prematurely

**When to reconsider**: If you reach €10-15K MRR and want to accelerate (hire sales, dev, marketing) to reach €50-100K MRR quickly.

**Non-dilutive funding options** (preferred if needed):
- BPI France "Innovation Development Aid": €30-45K
- Initiative France Honor Loan: €10-50K no guarantee
- Revenue-based financing (Uncapped): €50-500K repaid from future revenues

---

### Decision 3: Focus on Europe First

**Current stance**: Europe-focused (France, UK, Benelux, DACH).

**Why**:
- Underserved FinOps tools market in Europe
- Regulatory expertise (GDPR, French invoicing)
- Easier to close deals in your network
- Time zone advantage for support

**When to consider US**: After you have 15-20 European customers and €10-15K MRR stable. US market is saturated with competition.

---

## Risks & Mitigations

**Risk 1: Not enough beta testers**
*Mitigation*: Expand network (LinkedIn groups, Slack communities), offer AWS cost reimbursement (€50-100) if needed, accept starting with just 2 testers if feedback is very positive.

**Risk 2: Negative feedback from testers**
*Mitigation*: Fix critical bugs quickly, improve documentation if comprehension issue, don't launch commercially until utility score ≥7/10.

**Risk 3: No customer conversions in Phase 1**
*Mitigation*: Validate pricing with Phase 0 testers ("how much would you pay?"), offer personalized demos (not just self-service), adjust pricing if needed, consider pivot (managed service vs. SaaS).

**Risk 4: NDA violation by tester**
*Mitigation*: Rigorous tester selection (trust relationship), legally sound NDA, monitor GitHub access (Insights > Traffic), if violation occurs: immediate cease & desist + lawyer consultation.

**Risk 5: Critical bugs in production for paying customers**
*Mitigation*: Phase 0 testing should catch 90%+ of bugs, gradual rollout (max 2 customers/week initially), clear SLA (99% uptime, no guarantees at MVP stage), responsive support (reply to critical bugs within 4h).

---

## Next Actions (This Week)

**Top 3 priorities**:

1. **Read and validate all created documents** (NDA, guides, this strategy)
2. **Identify 5-10 potential testers** (actual names, not abstract)
3. **Send first outreach emails** (use template from `docs/BETA_TESTER_PITCH_EN.md`)

**Week-by-week plan for next 8 weeks**: See Phase 0 section above.

---

## Conclusion

You've built something valuable. Phase 1 MVP works. Now it's about validation and execution.

The strategy is clear:
1. Validate with beta testers (Phase 0)
2. Get first paying customers with self-hosted licenses (Phase 1)
3. Scale with AWS Marketplace (Phase 2)
4. Build from there

Keep it simple. Don't overcomplicate. Focus on customers, not features.

Revenue projections are conservative but achievable: €36-72K ARR in 6 months with excellent margins (90%+).

Stay bootstrapped as long as possible. The margins support it.

Go build.

---

**Document Version**: 2.0
**Author**: OptimNow
**Date**: January 9, 2025
**Next Review**: March 1, 2025 (after Phase 0 testing)
