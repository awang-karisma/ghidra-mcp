"""Direct file upload endpoint server (bypasses MCP protocol).

This standalone FastAPI server provides direct HTTP file upload endpoints
for agents to upload binary files without going through the MCP protocol.
"""

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from bridge_mcp_ghidra.config import logger
from bridge_mcp_ghidra.file_upload import validate_filename, ensure_file_root_directory


# Create FastAPI app
app = FastAPI(
    title="Ghidra MCP Direct File Upload",
    description="""
    Direct file upload endpoint for Ghidra MCP bridge.
    
    This server provides a simple HTTP API for uploading binary files directly,
    bypassing the MCP protocol layer. Files are stored in the directory configured
    by GHIDRA_MCP_FILE_ROOT environment variable.
    
    **Important**: Use this endpoint for:
    - Bulk file uploads
    - Large files (>10MB)
    - When you need raw HTTP control
    - When MCP protocol is not available
    
    For standard usage with AI agents, prefer calling the upload_file tool which 
    will guide you to use this direct HTTP endpoint.
    """,
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# File storage configuration
FILE_ROOT = os.getenv("GHIDRA_MCP_FILE_ROOT", "/tmp/ghidra-mcp-uploads")
UPLOAD_PORT = int(os.getenv("GHIDRA_MCP_UPLOAD_PORT", "8090"))


@app.get("/")
async def root():
    """Health check and usage information."""
    return {
        "service": "Ghidra MCP Direct File Upload",
        "status": "running",
        "upload_directory": FILE_ROOT,
        "endpoints": {
            "upload": "POST /upload",
            "list": "GET /files",
            "info": "GET /files/{filename}",
            "delete": "DELETE /files/{filename}"
        },
        "usage_examples": {
            "curl_upload": f"""
curl -X POST \\\\
  -F "file=@your_binary.so" \\\\
  http://localhost:{UPLOAD_PORT}/upload""",
            "curl_list": f"""
curl http://localhost:{UPLOAD_PORT}/files""",
            "python_requests": f"""
import requests

with open("your_binary.so", "rb") as f:
    response = requests.post(
        "http://localhost:{UPLOAD_PORT}/upload",
        files={{"file": f}}
    )
    
print(response.json())"""
        }
    }


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(..., description="Binary file to upload"),
    filename: Optional[str] = Form(None, description="Original filename (optional)"),
    content_type: Optional[str] = Form("application/octet-stream", description="MIME type")
):
    """
    Upload a binary file directly.
    
    Accepts multipart/form-data POST request with:
    - file: The binary file (required)
    - filename: Original filename (optional, defaults to original from request)
    - content_type: MIME type (optional, defaults to application/octet-stream)
    
    Returns the saved file path which can be used with other Ghidra tools.
    """
    try:
        # Validate if filename provided
        if filename and not validate_filename(filename):
            raise HTTPException(
                status_code=400,
                detail="Invalid filename. Only alphanumeric characters, underscore, dash, dot, and space are allowed."
            )
        
        # Ensure upload directory exists
        ensure_file_root_directory()
        
        # Get original filename from file object if not provided
        original_name = filename or file.filename or "uploaded_file"
        
        # Generate unique filename to prevent collisions
        file_extension = Path(original_name).suffix
        unique_filename = f"{uuid.uuid4().hex}{file_extension}"
        
        # Construct full path
        file_path = os.path.join(FILE_ROOT, unique_filename)
        relative_path = os.path.relpath(file_path, FILE_ROOT)
        full_path = os.path.abspath(file_path)
        
        # Save the file
        buffer_size = 0
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(8192):
                buffer.write(chunk)
                buffer_size += len(chunk)
        
        logger.info(f"Direct upload: {original_name} -> {relative_path} ({buffer_size} bytes)")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "original_filename": original_name,
                "saved_filename": unique_filename,
                "size": buffer_size,
                "content_type": content_type,
                "path": relative_path,
                "full_path": full_path,
                "message": f"File uploaded successfully via direct endpoint. Use path '{relative_path}' in Ghidra operations.",
                "endpoint_note": "This file was uploaded via the direct HTTP endpoint. You can now use it with Ghidra MCP tools."
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/files")
async def list_files(pattern: Optional[str] = Form(None)):
    """List all uploaded files with optional pattern filter."""
    try:
        ensure_file_root_directory()
        
        files = []
        for item in sorted(Path(FILE_ROOT).iterdir()):
            if item.is_file():
                if pattern and not item.match(pattern):
                    continue
                
                stat_info = item.stat()
                files.append({
                    "filename": item.name,
                    "size": stat_info.st_size,
                    "created": stat_info.st_ctime,
                    "modified": stat_info.st_mtime,
                    "path": item.name
                })
        
        return JSONResponse(
            status_code=200,
            content={
                "count": len(files),
                "files": files,
                "root": FILE_ROOT,
                "pattern": pattern,
                "endpoint_note": "Files uploaded here can be used with Ghidra MCP tools like import_file"
            }
        )
        
    except Exception as e:
        logger.error(f"List error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@app.get("/files/{filename:path}")
async def get_file_info(filename: str):
    """Get detailed information about an uploaded file."""
    try:
        ensure_file_root_directory()
        
        # Resolve path safely
        target_path = os.path.normpath(os.path.join(FILE_ROOT, filename))
        
        # Security check
        if not target_path.startswith(os.path.abspath(FILE_ROOT)):
            raise HTTPException(
                status_code=403,
                detail="Access denied: file path outside allowed directory"
            )
        
        if not os.path.exists(target_path):
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")
        
        if not os.path.isfile(target_path):
            raise HTTPException(status_code=400, detail=f"Path is not a file: {filename}")
        
        stat_info = os.stat(target_path)
        
        return JSONResponse(
            status_code=200,
            content={
                "exists": True,
                "filename": os.path.basename(target_path),
                "path": os.path.relpath(target_path, FILE_ROOT),
                "full_path": os.path.abspath(target_path),
                "size": stat_info.st_size,
                "created": stat_info.st_ctime,
                "modified": stat_info.st_mtime,
                "endpoint_note": "You can now use 'full_path' with import_file() MCP tool"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Info error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get file info: {str(e)}")


@app.delete("/files/{filename:path}")
async def delete_file(filename: str):
    """Delete an uploaded file."""
    try:
        ensure_file_root_directory()
        
        # Resolve path safely
        target_path = os.path.normpath(os.path.join(FILE_ROOT, filename))
        
        # Security check
        if not target_path.startswith(os.path.abspath(FILE_ROOT)):
            raise HTTPException(
                status_code=403,
                detail="Access denied: file path outside allowed directory"
            )
        
        if not os.path.exists(target_path):
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")
        
        if not os.path.isfile(target_path):
            raise HTTPException(status_code=400, detail=f"Path is not a file: {filename}")
        
        # Delete the file
        os.remove(target_path)
        
        logger.info(f"Direct delete: {filename}")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"File '{filename}' deleted successfully",
                "filename": os.path.basename(target_path)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")


if __name__ == "__main__":
    print("=" * 70)
    print("Ghidra MCP Direct File Upload Server")
    print("=" * 70)
    print(f"\nUpload directory: {FILE_ROOT}")
    print(f"Server port: {UPLOAD_PORT}")
    print(f"\nEndpoints:")
    print(f"  POST   /upload          - Upload a file")
    print(f"  GET    /files           - List all files")
    print(f"  GET    /files/{{filename}} - Get file info")
    print(f"  DELETE /files/{{filename}} - Delete a file")
    print(f"\nStart the server with: python3 -m bridge_mcp_ghidra.direct_upload_server")
    print("=" * 70)
    
    uvicorn.run(app, host="0.0.0.0", port=UPLOAD_PORT, log_level="info")
