"""Maps roles to agent configurations based on job settings."""


class RoleResolver:
    """Resolves which agent instance runs which role for a given job."""

    def __init__(self, job: dict, agents: dict):
        """
        Args:
            job: Job dict with planner_agent_id, coder_agent_id, tester_agent_id
            agents: Dict mapping agent_id -> agent dict (from DB)
        """
        self.job = job
        self.agents = agents

    def assign(self, role: str) -> dict:
        """Return the agent configuration for a given role."""
        col = {
            "planner": self.job.get("planner_agent_id"),
            "coder": self.job.get("coder_agent_id"),
            "tester": self.job.get("tester_agent_id"),
        }.get(role)

        if not col or col not in self.agents:
            raise ValueError(f"No agent configured for role: {role}")
        return self.agents[col]
