"""File upload validation and utility functions."""

import os
from pathlib import Path


def validate_filename(filename: str) -> bool:
    """Validate that a filename is safe (no path traversal attempts)."""
    # Check for null bytes
    if '\x00' in filename:
        return False
    
    # Check for path traversal attempts
    if filename.startswith('/') or '..' in filename:
        return False
    
    # Only allow alphanumeric, underscore, dash, dot, and space characters
    if not all(c.isalnum() or c in '._- ' for c in filename):
        return False
    
    return True


def ensure_file_root_directory():
    """Ensure the file root directory exists."""
    FILE_ROOT = os.getenv("GHIDRA_MCP_FILE_ROOT", "/tmp/ghidra-mcp-uploads")
    Path(FILE_ROOT).mkdir(parents=True, exist_ok=True)
    return FILE_ROOT
