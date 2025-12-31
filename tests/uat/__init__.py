# UAT (User Acceptance Testing) package for FinOps Tag Compliance MCP Server
#
# This package contains scenario-based tests designed to validate
# end-to-end agent behavior through AI assistants (Claude).
#
# Key characteristics:
# - Non-deterministic by nature (LLM outputs are probabilistic)
# - Use expectation-based assertions, not exact string matching
# - Run scenarios multiple times (N=3-5) to measure stability
# - Use LLM-as-a-judge for qualitative evaluation
#
# See scenarios.yaml for test definitions
# See GENAI_AND_AGENTSS_TESTING_GUIDELINES.md for methodology
