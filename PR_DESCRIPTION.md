# Simplify README and fix deployment issues

## Summary

This PR significantly improves documentation quality: simplifies README structure with engaging narrative style, fixes Windows deployment issues, adds video demo, and standardizes configuration approach based on user testing feedback.

## Key Changes

### 1. 📝 README Complete Rewrite
**Transformed from technical documentation to engaging narrative:**
- **Reduced length** from ~340 to ~200 lines (-142 lines, -42%)
- **Removed bullet points** in favor of flowing prose and storytelling
- **Added MCP education** section "For MCP Beginners" with clear mental models
- **Better analogies** - "phone line to infrastructure", "librarian who can only tell you which books exist"
- **Narrative use cases** - Real scenarios with dialogue instead of bullet lists
- **More conversational** - "Ever wished you could just ask Claude..." opening
- **Deployment content** moved to dedicated Deployment Guide
- **Video demo** added with Loom recording

**Why**: Make README inviting for MCP beginners while maintaining technical depth. Teach through storytelling instead of documentation style.

### 2. 🪟 Windows Deployment Support
Based on real user testing on Windows, added comprehensive support:

**New Files:**
- `docker-compose.windows.yml` - Windows-specific override file using `${USERPROFILE}/.aws`

**Updated Files:**
- `docker-compose.yml` - Now uses `~/.aws` for Linux/Mac
- `docs/DEPLOYMENT.md` - Added Windows-specific instructions throughout

**New Troubleshooting Sections:**
- Windows: Hidden .env.example file (show hidden files instructions)
- Windows: Docker mount denied error (File Sharing configuration)
- Orphan containers cleanup (brave_hermann issue)

### 3. 📺 Video Demo
Added Loom video demonstration in:
- README.md (Getting Started section)
- docs/DEPLOYMENT.md (before Next Steps)

Video shows: compliance checking, cost impact, ML suggestions, trends

### 4. 🔧 Port Fixes
Fixed all incorrect port 8000 references → 8080 in:
- README.md
- examples/claude_desktop_config_remote.json
- examples/README.md
- docs/TOOL_SEARCH_CONFIGURATION.md
- docs/diagrams/01-system-architecture.md
- docs/diagrams/05-deployment-architecture.md

### 5. 🌐 HTTP Bridge Simplification
Simplified deployment approach to use HTTP bridge for BOTH local and remote:

**Before:**
- Local: Docker stdio mode (complex, Docker-specific)
- Remote: HTTP bridge mode

**After:**
- Local: HTTP bridge with `http://localhost:8080`
- Remote: HTTP bridge with `http://your-server:8080`
- **Same configuration approach**, just different URL

**Benefits:**
- ✅ Consistent configuration for local and remote
- ✅ Easier to understand and troubleshoot
- ✅ Simpler to switch from local to remote
- ✅ No Docker stdio complexity


## Problems Solved

All issues from Windows user testing:
1. ✅ `.env.example` file not visible (hidden file)
2. ✅ Docker mount errors with `~/.aws` on Windows
3. ✅ Need for `${USERPROFILE}` instead of `~/.aws`
4. ✅ Docker File Sharing configuration not documented
5. ✅ "mounts denied" error on Windows
6. ✅ Orphan containers (`brave_hermann`) confusion
7. ✅ Port 8000 vs 8080 inconsistencies
8. ✅ Confusing dual-mode documentation (stdio vs HTTP)

## Files Changed

**Documentation:**
- README.md
- docs/DEPLOYMENT.md
- docs/TOOL_SEARCH_CONFIGURATION.md
- docs/diagrams/01-system-architecture.md
- docs/diagrams/05-deployment-architecture.md
- examples/README.md

**Configuration:**
- docker-compose.yml
- docker-compose.windows.yml (new)
- examples/claude_desktop_config_local.json
- examples/claude_desktop_config_remote.json

## Testing

✅ Validated with actual Windows user feedback
✅ All port references verified
✅ Docker Compose configurations tested
✅ Documentation accuracy confirmed

## Breaking Changes

None. Existing deployments continue to work. New approach is additive.

## Commits Summary

```
7f3dbc8 Rewrite README for engagement and accessibility
5e32f3a Add PR description document
49068a7 Simplify documentation: use HTTP bridge for both local and remote
a45fc85 Add video demo to README and Deployment Guide
7643a7e Add Windows-specific deployment support and troubleshooting
4ed3a37 Move Quick Start section to Deployment Guide
e7b808e Simplify README and fix port references
```
