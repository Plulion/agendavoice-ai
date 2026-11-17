# Google Gemini 2.5 Flash Integration (`R4.3.0`)

`agent.py` implements the branch-scoped conversational orchestrator (`run_branch_conversation_turn` and `build_branch_system_prompt`). Every tool execution is strictly bound to the authenticated `tenant_id` (via PostgreSQL RLS) and the target `branch_id`, ensuring the AI agent can never query or modify schedules or customers belonging to other branches.
