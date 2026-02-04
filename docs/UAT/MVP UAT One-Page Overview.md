## One-Page Overview

### The Problem

Almost half of cloud costs can't be properly attributed. That's according to the FinOps Foundation's 2025 report. The culprit? Missing or incorrect tags on AWS resources.

Compliance audits are manual and time-consuming. Two to three days per month, on average. Existing tools like CloudHealth and CloudCheckr are heavy and expensive. And none of them integrate with modern AI assistants.

The result? Millions in unattributable cloud spend. No way to optimize effectively. Frustrated FinOps teams.

### The Solution

I built the first MCP server dedicated to tagging compliance and FinOps optimization. It does a few key things really well.

Run compliance audits in seconds instead of days. Calculate your cost attribution gap automatically (the dollars you can't allocate). Get intelligent tag suggestions powered by machine learning. Apply bulk tagging with built-in approval workflows. It integrates natively with Claude Desktop. Supports 50+ AWS resource types.

How is it different? Compared to CloudHealth or CloudCheckr, it's simpler, cheaper, and AI-integrated. Compared to AWS native tools, it validates schemas, calculates cost impact, and provides suggestions. Compared to custom scripts, it's a packaged solution that's maintained and evolves.

### Current Status

Phase 1 MVP is complete as of January 2025. The MCP server runs on AWS EC2. It supports 50+ resource types. Full documentation is ready (technical and user guides). Internal tests are validated.

Next step is external validation with beta testers. Then commercial launch in Q1 2025, AWS Marketplace in Q2, multi-cloud support (Azure and GCP) in Q3.

### Beta Testing Program

I'm looking for 3-5 trusted testers. Ideal profile? Someone with 2+ years of FinOps, DevOps, or Cloud Architecture experience. AWS skills (IAM, EC2, tagging). Ability to provide structured feedback. Availability for 5-10 hours over 30-60 days.

What's required? You'd confirm a simple gentleman's agreement on confidentiality (the source code is still private). Deploy and test in your AWS environment with 50-100 resources minimum (a few hundred would be ideal). Provide a structured test report using a template I'll give you.

What do you get? Early adopter access to the first FinOps MCP on the market. Direct influence on the roadmap. A 50% lifetime discount if you become a customer (worth €300-600/month). For freelancers and consultants, potential resell or co-sell partnership opportunities. Optional recognition as a beta tester.

### Timeline

Week 1: Initial contact and confidentiality agreement signed. Onboarding, access to repo, deployment, support available. Weeks 3-4: Functional testing and continuous feedback. Week 5: Final report and cleanup (destroy all copies).

Start date is mid-January 2025. End date is beg-March 2025.

### Common Questions

**Is testing free?**  Only commitment is your time (5-10 hours) and if you deploy on an EC2 instance, a few dollars to run the MCP remote.

**Do I need a big AWS account?** Between 50 and 100 resources in total are enough to properly test the features. If you can manage to find an AWS account with a few hundred resources, that would be even better for comprehensive testing, but it's not required.

**What about security?** We've taken extra care with security from day one. The server scans your resources but doesn't store anything externally - everything stays in your AWS environment. You can find detailed documentation about our security posture and all the security tests we've conducted in the docs folder. We take security seriously, especially for a FinOps tool that accesses cloud infrastructure.

**I don't have much time, can I still participate?** I'd prefer someone who's committed. But if you're really interested and tight on time, let me know and we can adapt.

**Can I become a customer after?** Yes, absolutely. But it's more than that. If you're a freelancer or consultant, you could become a partner with resell or co-sell agreements. We're open to building strategic partnerships with people who see the value in the product.

**Will the code be open source?** Right now, no. There's significant effort and know-how embedded in this tool, so we're keeping it under a proprietary license. We need to focus on building a sustainable business model first. We might consider an Open Core model later based on market feedback, but for now the priority is on licensing. Your feedback on this approach is welcome though.

### Interested? Get in Touch

Email: jean@optimnow.io

Next steps: I'll send the confidentiality agreement and complete documentation. Once signed, you get GitHub access. We'll do onboarding and start testing.

Limited spots: Maximum 5 testers for this first wave.