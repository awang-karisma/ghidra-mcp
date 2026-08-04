# File Upload Guide for Ghidra MCP Bridge

## Overview

The Ghidra MCP bridge provides **two methods** for uploading binary files:

1. **Direct HTTP Endpoint** (Recommended) - Fast, bypasses MCP protocol overhead
2. **MCP Tool** (`upload_file`) - Rejected in favor of direct upload guidance

All uploaded files are stored in the directory configured by `GHIDRA_MCP_FILE_ROOT` environment variable.

---

## Recommended Method: Direct HTTP Upload

For most use cases, especially large files or bulk uploads, use the direct HTTP endpoint.

### Quick Start

```bash
# Upload a binary file
curl -X POST \
  -F "file=@module.so" \
  http://localhost:8090/upload
```

### Complete Workflow Example

```bash
#!/bin/bash

# Step 1: Upload file
RESPONSE=$(curl -s -X POST \
  -F "file=@target.so" \
  -F "filename=my_module.so" \
  http://localhost:8090/upload)

# Step 2: Extract path from response
FILE_PATH=$(echo "$RESPONSE" | jq -r '.full_path')

# Step 3: Use with import_file() MCP tool
import_file(
    file_path="$FILE_PATH",
    language="ELF:LE:32:i386",
    auto_analyze=true
)
```

---

## Configuration

### GHIDRA_MCP_FILE_ROOT

Set this environment variable to configure where uploaded files will be stored:

```bash
export GHIDRA_MCP_FILE_ROOT=/path/to/uploads
```

Default (if not set): `/tmp/ghidra-mcp-uploads`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GHIDRA_MCP_FILE_ROOT` | `/tmp/ghidra-mcp-uploads` | Directory for uploaded files |
| `GHIDRA_MCP_UPLOAD_PORT` | `8090` | Port for direct upload server |
| `GHIDRA_MCP_HOST` | `0.0.0.0` | Host binding for upload server |

---

## API Reference

### Starting the Upload Server

```bash
cd /path/to/ghidra-mcp/python
python3 -m bridge_mcp_ghidra.direct_upload_server
```

### POST /upload

Upload a binary file via multipart/form-data.

**Endpoint:** `POST http://localhost:8090/upload`

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | Binary file to upload |
| `filename` | String | No | Original filename |
| `content_type` | String | No | MIME type |

**Example cURL:**
```bash
curl -X POST \
  -F "file=@firmware.bin" \
  -F "filename=v1.2.3.bin" \
  -F "content_type=application/octet-stream" \
  http://localhost:8090/upload
```

**Python Example:**
```python
import requests

with open("firmware.bin", "rb") as f:
    response = requests.post(
        "http://localhost:8090/upload",
        files={"file": f}
    )

result = response.json()
print(f"Uploaded: {result['full_path']}")
```

### GET /files

List all uploaded files.

```bash
curl http://localhost:8090/files
```

### GET /files/{filename}

Get detailed information about a specific file.

```bash
curl http://localhost:8090/files/a1b2c3d4e5f6.so
```

### DELETE /files/{filename}

Delete an uploaded file.

```bash
curl -X DELETE http://localhost:8090/files/a1b2c3d4e5f6.so
```

---

## Response Format

Successful upload returns:

```json
{
  "success": true,
  "original_filename": "my_binary.so",
  "saved_filename": "a1b2c3d4e5f6789.so",
  "size": 2097152,
  "content_type": "application/x-sharedlib",
  "path": "a1b2c3d4e5f6789.so",
  "full_path": "/tmp/ghidra-mcp-uploads/a1b2c3d4e5f6789.so",
  "message": "File uploaded successfully via direct endpoint.",
  "endpoint_note": "This file was uploaded via the direct HTTP endpoint. You can now use it with Ghidra MCP tools."
}
```

**Use `full_path` with MCP tools like `import_file()`**

---

## AI Agent Integration

When integrating with AI agents, provide these instructions:

### File Upload Instructions for Agents

You have options for uploading binary files:

#### Option A: Direct HTTP Upload (Recommended)

Use the direct upload endpoint at `http://localhost:8090/upload`

**Best practices:**
- Files >10MB should use direct upload
- Use multipart/form-data for uploads
- Capture the `full_path` from response for Ghidra operations

**Example:**
```bash
RESPONSE=$(curl -s -X POST \
  -F "file=@target.so" \
  http://localhost:8090/upload)

FILE_PATH=$(echo "$RESPONSE" | jq -r '.full_path')
import_file(file_path="$FILE_PATH", ...)
```

#### Option B: MCP Tool (`upload_file`)

The `upload_file` MCP tool has been updated to reject uploads and provide guidance to use the direct HTTP endpoint instead. This ensures:
- Better performance (no base64 encoding)
- Support for larger files
- More control over upload process

**Note:** When `upload_file` is called, it returns information about the direct upload endpoint and examples for using it.

---

## Security Features

### Filename Validation

Uploaded filenames are validated:

- ✅ Allowed: alphanumeric, underscore `_`, dash `-`, dot `.`, space
- ❌ Blocked: Path traversal attempts (`../`)
- ❌ Blocked: Null bytes (`\x00`)
- ❌ Blocked: Absolute paths (`/path/to/file`)
- ❌ Blocked: Special characters (colons, backslashes)

### Production Hardening

1. **Set restrictive permissions:**
   ```bash
   export GHIDRA_MCP_FILE_ROOT=/secure/uploads
   chmod 700 $GHIDRA_MCP_FILE_ROOT
   ```

2. **Bind to localhost only** if not exposing externally:
   Edit `direct_upload_server.py` to use `host="127.0.0.1"`

3. **Add authentication** if needed:
   - API key header validation
   - Basic auth via reverse proxy
   - OAuth/JWT integration

4. **Monitor disk usage:**
   ```bash
   watch -n 5 du -sh $GHIDRA_MCP_FILE_ROOT
   ```

5. **Implement cleanup policy:**
   Auto-delete files older than N days

---

## Troubleshooting

### Server won't start

**Port already in use:**
```bash
lsof -i :8090
# Or use different port
export GHIDRA_MCP_UPLOAD_PORT=9000
python3 -m bridge_mcp_ghidra.direct_upload_server
```

### Upload fails with validation error

Only these characters allowed: a-z, A-Z, 0-9, `_`, `-`, `.`, space

Bad: `../../etc/passwd`, `file:name`  
Good: `my_file.so`, `sample file.bin`

### File not found after upload

1. Verify file was uploaded:
   ```bash
   curl http://localhost:8090/files
   ```

2. Check exact filename (includes UUID prefix):
   ```bash
   curl http://localhost:8090/files | jq -r '.files[].filename'
   ```

3. Use the `full_path` from upload response, not original filename

---

## Performance Tips

### For Large Files

1. Direct upload is ~10x faster than base64-encoded uploads
2. No memory duplication - streams directly to disk
3. Better error handling - partial uploads fail fast

### Batch Operations

```bash
#!/bin/bash
BINARY_DIR="./binaries"
UPLOAD_URL="http://localhost:8090/upload"

for file in $(find $BINARY_DIR -name "*.so"); do
    curl -s -X POST -F "file=@$file" $UPLOAD_URL
done
```

---

## Quick Reference

```
┌─────────────────────────────────────────────────┐
│         File Upload Quick Reference             │
├─────────────────────────────────────────────────┤
│                                                 │
│ UPLOAD (curl):                                  │
│ curl -F "file=@binary.so"                      │
│              http://localhost:8090/upload       │
│                                                  │
│ UPLOAD (Python):                                │
│ requests.post("http://localhost:8090/upload",   │
│              files={"file": open("bin.so","rb")})│
│                                                  │
│ LIST FILES:                                     │
│ curl http://localhost:8090/files                │
│                                                  │
│ FILE INFO:                                      │
│ curl http://localhost:8090/files/{filename}     │
│                                                  │
│ IMPORT TO GHIDRA:                               │
│ import_file(                                     │
│   file_path="/uploads/abc123def.so",           │
│   language="ELF:LE:32:i386",                    │
│   auto_analyze=True                              │
│ )                                               │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## Notes

- All uploaded files respect `GHIDRA_MCP_FILE_ROOT` configuration
- Returned `full_path` is directly compatible with `import_file()` and other MCP tools
- Files remain accessible until manually deleted or cleaned up
- Works seamlessly with existing Ghidra analysis workflows
