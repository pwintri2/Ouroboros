#!/usr/bin/env python3
"""Negesydd App - Multi-Agent Messenger System."""

import sys
import argparse
import json

def setup_environment():
    """Initialize environment and check dependencies."""
    print("🚀 Initializing Negesydd Multi-Agent Messenger System...\n")
    
    required_modules = []
    optional_modules = ['requests', 'flask', 'ollama', 'yaml']
    missing = []
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"  ✓ {module} available")
        except ImportError:
            missing.append(module)
            print(f"  ✗ {module} NOT FOUND")

    for module in optional_modules:
        try:
            __import__(module)
            print(f"  ✓ {module} available")
        except ImportError:
            print(f"  ⚠️  {module} not installed")
    
    if missing:
        print(f"\n⚠️  Missing required dependencies: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt\n")
        return False
    
    print("\n✓ Core runtime ready\n")
    return True

def check_ollama():
    """Verify Ollama is running and deepseek-coder is available."""
    print("Checking Ollama setup...")
    try:
        import requests
        response = requests.get('http://localhost:11434/api/tags', timeout=2)
        tags = response.json().get('models', [])
        
        deepseek_available = any('deepseek-coder' in tag.get('name', '') for tag in tags)
        
        if deepseek_available:
            print("  ✓ Ollama is running")
            print("  ✓ deepseek-coder:latest is available\n")
            return True
        else:
            print("  ✓ Ollama is running")
            print("  ⚠️  deepseek-coder:latest not found")
            print("     Run: ollama pull deepseek-coder:latest\n")
            return False
    except Exception as e:
        print(f"  ✗ Ollama not responding: {e}")
        print("     Start Ollama with: ollama serve\n")
        return False

def check_gemini_cli():
    """Check if Gemini CLI is available."""
    print("Checking Gemini CLI...")
    try:
        import subprocess
        result = subprocess.run(['which', 'gemini'], capture_output=True)
        if result.returncode == 0:
            print("  ✓ Gemini CLI found\n")
            return True
        else:
            print("  ⚠️  Gemini CLI not found in PATH\n")
            return False
    except:
        print("  ⚠️  Could not locate Gemini CLI\n")
        return False

def discover_agents():
    """Discover available agents in the system."""
    print("Discovering agents...")
    agents = []
    
    # Check for common agent executables
    agent_names = ['goose', 'gorilla']
    for agent in agent_names:
        try:
            import subprocess
            result = subprocess.run(['which', agent], capture_output=True)
            if result.returncode == 0:
                agents.append(agent)
                print(f"  ✓ {agent} agent detected")
        except:
            pass
    
    print(f"  Found {len(agents)} agent(s)\n")
    return agents

def list_available_llms():
    """List all available LLMs for routing."""
    print("Available LLMs in Ollama:")
    try:
        import requests
        response = requests.get('http://localhost:11434/api/tags', timeout=2)
        tags = response.json().get('models', [])
        for tag in tags:
            name = tag.get('name', 'unknown')
            print(f"  • {name}")
    except:
        print("  (Ollama not available)")
    print()

def main():
    parser = argparse.ArgumentParser(
        description='Negesydd - Multi-Agent Messenger System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXAMPLES:

  # Load a plan file
  %(prog)s --plan plans/example_workflow.yaml

  # Start with an inline prompt
  %(prog)s --prompt "Build a REST API with FastAPI" --agents gorilla,goose

  # Discover available agents
  %(prog)s --discover-agents

  # Check system readiness
  %(prog)s --check-system

  # Load and execute with verbose logging
  %(prog)s --plan plans/example_workflow.yaml --verbose --loglevel DEBUG

  # Dry-run mode (plan only, no execution)
  %(prog)s --plan plans/example_workflow.yaml --dry-run

  # Start dashboard
  %(prog)s --dashboard

  # Start native desktop dashboard
  %(prog)s --desktop

  # List available LLMs
  %(prog)s --list-llms
        """
    )
    
    parser.add_argument('--plan', type=str, help='Path to YAML plan file')
    parser.add_argument('--prompt', type=str, help='Inline prompt text')
    parser.add_argument('--agents', type=str, help='Comma-separated list of agents to use')
    parser.add_argument('--discover-agents', action='store_true', help='Discover available agents')
    parser.add_argument('--check-system', action='store_true', help='Check system readiness')
    parser.add_argument('--list-llms', action='store_true', help='List available LLMs')
    parser.add_argument('--dashboard', action='store_true', help='Start the dashboard UI')
    parser.add_argument('--desktop', action='store_true', help='Start the native desktop UI')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--dry-run', action='store_true', help='Parse and validate without execution')
    parser.add_argument('--loglevel', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                        default='INFO', help='Logging level')
    parser.add_argument('--port', type=int, default=8765, help='Dashboard port (default: 8765)')
    
    args = parser.parse_args()

    if args.dashboard:
        from dashboard import DashboardServer
        print(f"Starting Negesydd dashboard at http://127.0.0.1:{args.port}")
        DashboardServer(port=args.port).start(debug=args.verbose)
        sys.exit(0)

    if args.desktop:
        from negesydd_desktop import main as desktop_main
        sys.exit(desktop_main())
    
    # System checks
    if args.check_system:
        print("\n" + "="*60)
        print("SYSTEM READINESS CHECK")
        print("="*60 + "\n")
        
        ready = setup_environment()
        ollama_ok = check_ollama()
        gemini_ok = check_gemini_cli()
        agents = discover_agents()
        
        print("="*60)
        print("STATUS SUMMARY")
        print("="*60)
        print(f"Dependencies:     {'✓ OK' if ready else '✗ MISSING'}")
        print(f"Ollama:           {'✓ OK' if ollama_ok else '✗ NOT READY'}")
        print(f"Gemini CLI:       {'✓ OK' if gemini_ok else '⚠️  NOT FOUND'}")
        print(f"Agents Found:     {len(agents)} ({', '.join(agents)})")
        print("="*60 + "\n")
        
        sys.exit(0)
    
    # List LLMs
    if args.list_llms:
        print()
        list_available_llms()
        print("Recommended for Negesydd: deepseek-coder:latest (optimal for routing/reasoning)\n")
        sys.exit(0)
    
    # Discover agents
    if args.discover_agents:
        print()
        agents = discover_agents()
        print("="*60)
        if agents:
            print(f"✓ Found {len(agents)} agent(s) ready for use\n")
        else:
            print("⚠️  No agents detected. Install gorilla/goose agents.\n")
        sys.exit(0)
    
    # Main execution
    if args.plan or args.prompt:
        print("\n" + "="*60)
        print("NEGESYDD - MULTI-AGENT MESSENGER SYSTEM")
        print("="*60 + "\n")
        
        if not setup_environment():
            print("❌ System not ready. Run: negesydd --check-system\n")
            sys.exit(1)
        
        check_ollama()
        
        from config_parser import ConfigParser
        from lifecycle import LifecycleManager
        from logger import StructuredLogger

        logger = StructuredLogger("negesydd", level=args.loglevel)
        lifecycle = LifecycleManager(logger=logger)

        selected_agents = [agent.strip() for agent in args.agents.split(",") if agent.strip()] if args.agents else None
        if args.plan:
            config = ConfigParser.from_file(args.plan)
        else:
            config = ConfigParser.from_prompt(args.prompt or "", agents=selected_agents)

        if args.dry_run:
            print("DRY-RUN MODE\n")
            print(config.to_string())
            sys.exit(0)

        report = lifecycle.execute(config)
        print("\nExecution complete\n")
        print(json.dumps(report.to_dict(), indent=2, default=str))
        sys.exit(0 if report.success else 1)
    
    # No arguments
    parser.print_help()
    print("\nStart with: python negesydd_app.py --check-system\n")

if __name__ == '__main__':
    main()
