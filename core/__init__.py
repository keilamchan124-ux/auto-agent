"""Core package for Agent V7.2.

This package intentionally avoids eager submodule imports to prevent
side effects at import time (for example, API client initialization).
Import required modules explicitly, e.g.:

- from core import tools
- from core.agent import Agent
"""

__all__ = [
    "agent",
    "config",
    "llm",
    "tools",
]
