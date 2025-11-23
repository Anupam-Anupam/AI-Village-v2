#!/usr/bin/env python3
"""
Task execution script for agent worker.
This script receives a task description and executes it using the CUA agent.

Usage:
    python execute_task.py "task description"
    or
    TASK_DESCRIPTION="task description" python execute_task.py
"""

import sys
import os
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional, Any

# Load .env file if it exists
load_dotenv()

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Add CUA to path
cua_path = project_root / "CUA"
if cua_path.exists():
    sys.path.insert(0, str(cua_path))

# Add agent_worker to path for imports
agent_worker_path = Path(__file__).parent
sys.path.insert(0, str(agent_worker_path))

# In Docker, code is at /app/agent_worker/, so adjust paths
if Path("/app/agent_worker").exists():
    sys.path.insert(0, "/app")
    sys.path.insert(0, "/app/agent_worker")
    if Path("/app/CUA").exists():
        sys.path.insert(0, "/app/CUA")


def get_task_description():
    """Get task description from command line or environment."""
    if len(sys.argv) > 1:
        # Get from command line arguments
        task_description = " ".join(sys.argv[1:])
    else:
        # Get from environment variable
        task_description = os.getenv("TASK_DESCRIPTION", "")
    
    return task_description  # Return empty string if not provided (for polling mode)


async def execute_task_async(task_description: str, task_id: Optional[int] = None, mongo_client: Optional[Any] = None) -> dict:
    """
    Execute a task using CUA agent and return results.
    
    Args:
        task_description: The task description to execute
        task_id: Optional task ID for logging
        mongo_client: Optional MongoDB client for trajectory processing
        
    Returns:
        Dictionary with execution results
    """
    result = {
        "status": "success",
        "output": "",
        "error": None
    }
    
    try:
        # Check for required environment variables
        cua_api_key = os.getenv("CUA_API_KEY")
        cua_sandbox_name = os.getenv("CUA_SANDBOX_NAME", "default")
        openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if not cua_api_key or not openai_api_key:
            missing = [k for k, v in [("CUA_API_KEY", cua_api_key), ("OPENAI_API_KEY", openai_api_key)] if not v]
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        # Import CUA packages
        from agent import ComputerAgent
        from computer import Computer, VMProviderType
        
        # Create computer instance
        computer = Computer(
            os_type="linux",
            api_key=cua_api_key,
            name=cua_sandbox_name,
            provider_type=VMProviderType.CLOUD,
        )
        
        # Set up trajectory directory (like example.py)
        # Use workdir if provided, otherwise current directory
        workdir = os.getenv("WORKDIR")
        if workdir:
            trajectory_dir = Path(workdir) / "trajectories"
        else:
            trajectory_dir = Path("trajectories")
        
        # CUA will create the directory structure automatically
        # But we ensure parent exists so it's visible
        trajectory_dir.mkdir(parents=True, exist_ok=True)
        
        # Start trajectory processor if MongoDB client provided
        trajectory_observer = None
        if mongo_client:
            try:
                # Ensure agent_worker directory is in path for imports
                agent_worker_dir = str(Path(__file__).parent)
                if agent_worker_dir not in sys.path:
                    sys.path.insert(0, agent_worker_dir)
                
                # Also try /app/agent_worker if in Docker
                if Path("/app/agent_worker").exists() and "/app/agent_worker" not in sys.path:
                    sys.path.insert(0, "/app/agent_worker")
                
                # Try multiple import paths
                try:
                    from trajectory_processor import start_processor
                except ImportError:
                    try:
                        from agent_worker.trajectory_processor import start_processor
                    except ImportError:
                        # Direct file import as fallback
                        import importlib.util
                        possible_paths = [
                            Path(__file__).parent / "trajectory_processor.py",
                            Path("/app/agent_worker/trajectory_processor.py"),
                        ]
                        processor_path = None
                        for path in possible_paths:
                            if path.exists():
                                processor_path = path
                                break
                        
                        if processor_path and processor_path.exists():
                            spec = importlib.util.spec_from_file_location("trajectory_processor", processor_path)
                            trajectory_processor_module = importlib.util.module_from_spec(spec)
                            trajectory_processor_module.__package__ = "agent_worker"
                            trajectory_processor_module.__name__ = "agent_worker.trajectory_processor"
                            sys.modules["trajectory_processor"] = trajectory_processor_module
                            sys.modules["agent_worker.trajectory_processor"] = trajectory_processor_module
                            spec.loader.exec_module(trajectory_processor_module)
                            start_processor = trajectory_processor_module.start_processor
                        else:
                            raise ImportError("trajectory_processor.py not found")
                
                trajectory_observer = start_processor(trajectory_dir, mongo_client, task_id)
            except Exception as e:
                # Log error but don't fail - trajectory processor is optional
                print(f"Warning: Failed to start trajectory processor: {e}", file=sys.stderr)
        
        # Create agent (like example.py)
        agent = ComputerAgent(
            model="omniparser+openai/gpt-4o",
            tools=[computer],
            only_n_most_recent_images=3,
            verbosity=logging.WARNING,
            trajectory_dir=str(trajectory_dir),
        )
        
        # Execute task (like example.py)
        history = [{"role": "user", "content": task_description}]
        collected_outputs = []
        
        async for result_item in agent.run(history, stream=False):
            # Add agent outputs to history (matches example.py)
            history += result_item.get("output", [])
            
            # Collect text messages
            for item in result_item.get("output", []):
                if item.get("type") == "message":
                    content = item.get("content", [])
                    for content_part in content:
                        if isinstance(content_part, dict) and content_part.get("text"):
                            collected_outputs.append(content_part.get("text"))
        
        if collected_outputs:
            result["output"] = "\n".join(collected_outputs)
        else:
            result["output"] = "Task executed but no text output received"
            
    except ImportError as e:
        result["output"] = f"Task received: {task_description}\nTask execution failed - CUA agent not available: {str(e)}"
        result["status"] = "error"
        result["error"] = str(e)
    except ValueError as e:
        result["output"] = f"Task received: {task_description}\nConfiguration error: {str(e)}"
        result["status"] = "error"
        result["error"] = str(e)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"Error executing task: {e}", file=sys.stderr)
    
    return result


def execute_task(task_description: str, task_id: Optional[int] = None, mongo_client: Optional[Any] = None) -> dict:
    """
    Synchronous wrapper for async task execution.
    
    Args:
        task_description: The task description to execute
        
    Returns:
        Dictionary with execution results
    """
    # Use asyncio.run() for Python 3.7+ (handles event loop creation/cleanup automatically)
    # This avoids the deprecation warning from get_event_loop()
    # asyncio.run() will raise RuntimeError if called from within an async context,
    # which is the correct behavior
    return asyncio.run(execute_task_async(task_description, task_id, mongo_client))


def main():
    """Main entry point."""
    task_description = get_task_description()
    
    # If no task description provided, run in polling mode using runner
    if not task_description:
        try:
            from config import Config
            from db_adapters import PostgresClient, MongoClientWrapper
            from runner import AgentRunner
            
            # Load configuration and start polling loop
            config = Config.from_env()
            postgres = PostgresClient(config.postgres_dsn)
            mongo = MongoClientWrapper(config.mongo_uri, config.agent_id)
            
            runner = AgentRunner(
                config=config,
                postgres_client=postgres,
                mongo_client=mongo
            )
            
            runner.poll_loop()
        except KeyboardInterrupt:
            print("\nShutting down agent worker...")
            sys.exit(0)
        except Exception as e:
            print(f"Fatal error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        return
    
    # Single task execution mode
    # Get task_id and mongo_client from environment if available
    task_id = None
    mongo_client = None
    
    task_id_str = os.getenv("TASK_ID")
    if task_id_str:
        try:
            task_id = int(task_id_str)
        except:
            pass
    
    mongo_uri = os.getenv("MONGO_URI")
    agent_id = os.getenv("AGENT_ID")
    if mongo_uri and agent_id:
        try:
            from db_adapters import MongoClientWrapper
            mongo_client = MongoClientWrapper(mongo_uri, agent_id)
        except Exception as e:
            print(f"Warning: Failed to initialize MongoDB client: {e}", file=sys.stderr)
    
    result = execute_task(task_description, task_id=task_id, mongo_client=mongo_client)
    
    # Output only the clean agent response (no diagnostics)
    print("AGENT_RESPONSE_START")
    if result.get('output'):
        print(result['output'].strip())
    elif result.get('error'):
        print(f"Error: {result['error']}")
    else:
        print("No output or error")
    print("AGENT_RESPONSE_END")
    
    # Exit with appropriate code
    if result['status'] == 'success':
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

