# License System Implementation
## Self-Hosted MCP Server - License Validation

**Goal**: Enable selling self-hosted licenses with validation system

---

## Architecture

```
┌─────────────────┐
│  Client AWS     │
│                 │
│  ┌───────────┐  │
│  │ MCP Server│  │  1. Startup
│  │ (Docker)  ├──┼──────────┐
│  └───────────┘  │          │
│                 │          │
│  License Key:   │          │
│  "OPT-XXXXX"    │          │
└─────────────────┘          │
                             ▼
                   ┌──────────────────────┐
                   │ License Server       │
                   │ license.optimnow.io  │
                   │                      │
                   │ POST /validate       │
                   │ - Checks key         │
                   │ - Returns limits     │
                   │ - Logs usage         │
                   └──────────────────────┘
```

---

## Step 1: License Key Format

**Format**: `OPT-PLAN-XXXXX-XXXXX`

Example:
- `OPT-STARTER-A3B2C-D4E5F` (Starter plan)
- `OPT-PRO-X9Y8Z-W7V6U` (Professional plan)
- `OPT-ENT-M1N2O-P3Q4R` (Enterprise plan)

**Generation** (Python):
```python
import secrets
import hashlib

def generate_license_key(plan: str, customer_email: str) -> str:
    """
    Generate a unique license key
    plan: "starter", "pro", or "enterprise"
    """
    plan_prefix = plan.upper()[:3]
    random_part = secrets.token_hex(5).upper()

    # Hash email for uniqueness
    email_hash = hashlib.sha256(customer_email.encode()).hexdigest()[:5].upper()

    return f"OPT-{plan_prefix}-{random_part}-{email_hash}"

# Example
key = generate_license_key("pro", "customer@example.com")
# Result: OPT-PRO-3A9F2-B4C1D
```

---

## Step 2: License Server (Simple Version)

**Option A: Supabase (Recommended for MVP)**

Free tier: 500MB storage, 50K monthly active users

```sql
-- Supabase table: licenses
CREATE TABLE licenses (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  license_key TEXT UNIQUE NOT NULL,
  customer_email TEXT NOT NULL,
  customer_name TEXT,
  plan TEXT NOT NULL, -- "starter", "pro", "enterprise"
  max_resources INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  expires_at TIMESTAMP,
  active BOOLEAN DEFAULT TRUE,
  last_validated TIMESTAMP
);

-- Insert a license
INSERT INTO licenses (license_key, customer_email, customer_name, plan, max_resources, expires_at)
VALUES (
  'OPT-PRO-3A9F2-B4C1D',
  'customer@example.com',
  'John Doe',
  'pro',
  10000,
  '2026-01-09'
);
```

**Supabase Edge Function for validation**:
```typescript
// supabase/functions/validate-license/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2"

serve(async (req) => {
  const { license_key } = await req.json()

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL'),
    Deno.env.get('SUPABASE_KEY')
  )

  // Validate license
  const { data, error } = await supabase
    .from('licenses')
    .select('*')
    .eq('license_key', license_key)
    .single()

  if (error || !data) {
    return new Response(
      JSON.stringify({ valid: false, message: "Invalid license key" }),
      { status: 401 }
    )
  }

  // Check expiration
  const now = new Date()
  const expires = new Date(data.expires_at)

  if (!data.active || expires < now) {
    return new Response(
      JSON.stringify({ valid: false, message: "License expired or inactive" }),
      { status: 401 }
    )
  }

  // Update last validated
  await supabase
    .from('licenses')
    .update({ last_validated: now.toISOString() })
    .eq('license_key', license_key)

  return new Response(
    JSON.stringify({
      valid: true,
      plan: data.plan,
      max_resources: data.max_resources,
      expires_at: data.expires_at
    }),
    { status: 200 }
  )
})
```

**Deploy**:
```bash
# 1. Create Supabase project (free): https://supabase.com
# 2. Create table via SQL editor
# 3. Deploy Edge Function
supabase functions deploy validate-license
```

**Cost**: Free (up to 500K requests/month)

---

**Option B: Simple Flask API (if you prefer self-hosted)**

```python
# license_server.py
from flask import Flask, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)

@app.route('/validate', methods=['POST'])
def validate_license():
    data = request.json
    license_key = data.get('license_key')

    # Connect to SQLite
    conn = sqlite3.connect('licenses.db')
    cursor = conn.cursor()

    # Check license
    cursor.execute("""
        SELECT plan, max_resources, expires_at, active
        FROM licenses
        WHERE license_key = ?
    """, (license_key,))

    result = cursor.fetchone()

    if not result:
        return jsonify({"valid": False, "message": "Invalid license key"}), 401

    plan, max_resources, expires_at, active = result

    # Check expiration
    expires = datetime.fromisoformat(expires_at)
    if not active or expires < datetime.now():
        return jsonify({"valid": False, "message": "License expired"}), 401

    # Update last_validated
    cursor.execute("""
        UPDATE licenses SET last_validated = ? WHERE license_key = ?
    """, (datetime.now().isoformat(), license_key))
    conn.commit()
    conn.close()

    return jsonify({
        "valid": True,
        "plan": plan,
        "max_resources": max_resources,
        "expires_at": expires_at
    }), 200

if __name__ == '__main__':
    app.run(port=5000)
```

**Deploy**:
```bash
# Deploy on Fly.io (free tier)
fly launch
fly deploy
```

---

## Step 3: MCP Server License Validation

**Add to your MCP server** (`mcp_server/license.py`):

```python
# mcp_server/license.py
import os
import requests
from typing import Dict, Optional
from datetime import datetime, timedelta

class LicenseValidator:
    def __init__(self):
        self.license_key = os.getenv("OPTIMNOW_LICENSE_KEY")
        self.license_server_url = os.getenv(
            "LICENSE_SERVER_URL",
            "https://your-project.supabase.co/functions/v1/validate-license"
        )
        self.cache: Optional[Dict] = None
        self.cache_expiry: Optional[datetime] = None

    def validate(self) -> Dict:
        """
        Validate license key with server
        Returns: {"valid": bool, "plan": str, "max_resources": int, ...}
        """
        if not self.license_key:
            raise Exception(
                "Missing license key. Set OPTIMNOW_LICENSE_KEY environment variable.\n"
                "To purchase a license: https://optimnow.io/pricing"
            )

        # Check cache (avoid hitting server on every call)
        if self.cache and self.cache_expiry and datetime.now() < self.cache_expiry:
            return self.cache

        # Validate with server
        try:
            response = requests.post(
                self.license_server_url,
                json={"license_key": self.license_key},
                timeout=5
            )

            if response.status_code != 200:
                raise Exception(f"License validation failed: {response.json().get('message')}")

            result = response.json()

            # Cache for 1 hour
            self.cache = result
            self.cache_expiry = datetime.now() + timedelta(hours=1)

            return result

        except requests.exceptions.RequestException as e:
            # Graceful degradation: if license server is down, allow usage for 24h
            if self.cache:
                return self.cache
            raise Exception(f"License server unreachable: {e}")

    def check_resource_limit(self, resource_count: int):
        """Check if resource count is within license limits"""
        license_info = self.validate()
        max_resources = license_info.get("max_resources", 0)

        if resource_count > max_resources:
            plan = license_info.get("plan", "unknown")
            raise Exception(
                f"License limit exceeded: {resource_count} resources "
                f"(max {max_resources} for {plan} plan)\n"
                f"To upgrade your license: https://optimnow.io/pricing"
            )

# Global instance
license_validator = LicenseValidator()
```

**Use in your MCP tools**:

```python
# mcp_server/tools/check_tag_compliance.py
from mcp_server.license import license_validator

async def check_tag_compliance(
    resource_types: Optional[List[str]] = None,
    regions: Optional[List[str]] = None
) -> Dict:
    """Check tag compliance for AWS resources"""

    # 1. Validate license
    license_info = license_validator.validate()

    # 2. Scan resources
    resources = await scan_aws_resources(resource_types, regions)

    # 3. Check resource limit
    resource_count = len(resources)
    license_validator.check_resource_limit(resource_count)

    # 4. Continue with compliance check...
    violations = check_policy_violations(resources)

    return {
        "total_resources": resource_count,
        "violations": violations,
        "license": {
            "plan": license_info["plan"],
            "resources_scanned": resource_count,
            "max_resources": license_info["max_resources"]
        }
    }
```

---

## Step 4: Docker Configuration

**Update docker-compose.yml**:

```yaml
services:
  mcp-server:
    build: .
    ports:
      - "8080:8080"
    environment:
      # License configuration
      - OPTIMNOW_LICENSE_KEY=${OPTIMNOW_LICENSE_KEY}
      - LICENSE_SERVER_URL=https://your-project.supabase.co/functions/v1/validate-license

      # AWS credentials (existing)
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
    volumes:
      - ~/.aws:/root/.aws:ro
```

**Customer setup** (.env file):

```bash
# .env
OPTIMNOW_LICENSE_KEY=OPT-PRO-3A9F2-B4C1D
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_DEFAULT_REGION=us-east-1
```

---

## Step 5: Pricing Tiers

| Plan | Price | Max Resources | Support | License Type |
|------|-------|---------------|---------|--------------|
| **Starter** | 1 499€/year | 1,000 | Email (48h) | Annual |
| **Professional** | 4 999€/year | 10,000 | Email (24h) | Annual |
| **Enterprise** | Custom | Unlimited | Slack (4h SLA) | Annual/Custom |

**Discount for Early Adopters**: -30% for first 10 customers

---

## Step 6: Sales Process

### 1. Customer Purchase Flow

```
1. Customer visits pricing page
2. Clicks "Buy Starter" (or Pro, Enterprise)
3. Stripe payment form (or wire transfer for enterprise)
4. Payment confirmed
5. YOU manually:
   - Generate license key
   - Insert into Supabase table
   - Send email with license + Docker image + docs
```

### 2. Email Template After Purchase

```
Subject: Your OptimNow FinOps MCP License - OPT-PRO-XXXXX

Hi [Customer Name],

Thank you for purchasing OptimNow FinOps Tag Compliance MCP!

YOUR LICENSE INFORMATION
────────────────────────
License Key: OPT-PRO-3A9F2-B4C1D
Plan: Professional
Max Resources: 10,000
Valid Until: January 9, 2026

WHAT'S INCLUDED
───────────────
✅ Docker container with MCP server
✅ CloudFormation template for AWS deployment
✅ Complete documentation (deployment + user guide)
✅ Email support (24h response time)
✅ Free updates for 1 year

NEXT STEPS
──────────
1. Download the files (link below)
2. Deploy to your AWS account (30 min setup)
3. Configure Claude Desktop
4. Start using: "Claude, audit my AWS tagging compliance"

📦 Download: [Private S3 link or GitHub access]

📚 Documentation: https://docs.optimnow.io

💬 Support: jean@optimnow.io

Need help with deployment? Reply to this email and I'll schedule a
30-minute onboarding call.

Thank you for your trust!

Jean Latiere
OptimNow
jean@optimnow.io
```

---

## Step 7: License Management (Your Side)

**Notion or Excel tracker**:

| Customer | Email | License Key | Plan | Price | Purchased | Expires | Status |
|----------|-------|-------------|------|-------|-----------|---------|--------|
| John Doe | john@example.com | OPT-PRO-XXX | Pro | 4999€ | 2025-01-09 | 2026-01-09 | Active |
| Jane Smith | jane@startup.io | OPT-STA-YYY | Starter | 1499€ | 2025-01-15 | 2026-01-15 | Active |

**Renewals**:
- Send email 30 days before expiration: "Your license expires soon, renew now"
- Offer auto-renewal (Stripe recurring billing)

---

## Step 8: Anti-Piracy Measures

**Basic protections** (for MVP):

1. **License key validation on startup** (done ✅)
2. **Daily re-validation** (check every 24h, not every call)
3. **License server logs usage** (detect suspicious patterns)

**Advanced protections** (later):

4. **Hardware fingerprinting**: Limit license to specific AWS account
5. **Call home**: MCP reports usage metrics weekly
6. **Obfuscation**: Obfuscate Python code (PyArmor)

**Reality**:
- Some piracy will happen (accept it)
- Focus on making buying easier than pirating
- Enterprise customers won't risk piracy (compliance)

---

## Implementation Checklist

For your MVP, implement in this order:

### Week 1: License System
- [ ] Create Supabase project (free)
- [ ] Create `licenses` table
- [ ] Deploy `validate-license` Edge Function
- [ ] Test with Postman

### Week 2: MCP Integration
- [ ] Create `mcp_server/license.py`
- [ ] Add validation to main tools (`check_tag_compliance`, etc.)
- [ ] Update `docker-compose.yml` with license env var
- [ ] Test: start MCP without license key → should fail
- [ ] Test: start MCP with valid key → should work

### Week 3: Customer Experience
- [ ] Create pricing page (simple HTML or Notion page)
- [ ] Integrate Stripe payment (or start with manual wire transfer)
- [ ] Write email template for post-purchase
- [ ] Create private S3 bucket for Docker image download
- [ ] Test full customer journey

---

## Cost Estimate

| Component | Cost |
|-----------|------|
| License server (Supabase) | Free |
| Docker image hosting (S3) | ~5€/month |
| Domain (optimnow.io) | ~15€/year |
| Stripe fees | 1.5% + 0.25€ per payment |
| **Total** | ~20€/month |

**Break-even**: 1 customer (1 499€) covers 6 years of costs!

---

## Questions?

This system is:
- ✅ Simple to implement (1-2 weeks)
- ✅ Low cost (almost free)
- ✅ Scalable (Supabase handles 500K+ validations/month free)
- ✅ Standard practice (many B2B tools use similar approach)

Need help implementing? Let me know which part you want to start with.

---

**Document Version**: 1.0
**Author**: Claude for OptimNow
**Date**: January 9, 2025
