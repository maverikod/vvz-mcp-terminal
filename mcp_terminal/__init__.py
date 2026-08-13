"""
MCP-facing OpenAPI terminal service: shell in a container with a mounted
project workspace.

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from mcp_terminal.package_info import package_version as _package_version

__version__ = _package_version()
