from datetime import datetime, timedelta

from agent_pool import Agent, AgentPool, AgentStatus


def test_agent_pool_init():
    """Test AgentPool initialization."""
    pool = AgentPool()
    assert pool.agents == {}


def test_discover_agents():
    """Test agent discovery."""
    pool = AgentPool()
    agents = pool.discover_agents()
    assert agents
    assert pool.list_all_agents()


def test_add_agent():
    """Test adding agent to pool."""
    pool = AgentPool()
    agent = Agent(
        agent_id="test_1",
        name="Test Agent",
        status=AgentStatus.IDLE,
        last_heartbeat=datetime.now(),
        uptime_seconds=100,
        capability_tags=["test"],
    )
    pool.add_agent(agent)
    assert pool.get_agent("test_1") is not None


def test_agent_health_check():
    """Test agent health monitoring."""
    pool = AgentPool()
    agent = Agent(
        agent_id="test_1",
        name="Test",
        status=AgentStatus.IDLE,
        last_heartbeat=datetime.now(),
        uptime_seconds=100,
    )
    pool.add_agent(agent)
    assert agent.is_healthy()


def test_unhealthy_stale_agent():
    agent = Agent(
        agent_id="test_1",
        name="Test",
        status=AgentStatus.IDLE,
        last_heartbeat=datetime.now() - timedelta(seconds=60),
        uptime_seconds=100,
    )
    assert not agent.is_healthy()

