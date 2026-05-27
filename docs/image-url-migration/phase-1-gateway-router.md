# Phase 1：新增 Gateway 图片文件服务路由

## 目标

新增一个 FastAPI 路由，提供经过认证的图片文件访问服务。LLM 和前端都可以通过此端点获取图片。

## 路由设计

- **端点**: `GET /api/threads/{thread_id}/files/image/{path:path}`
- **认证**: `@require_auth` + `@require_permission("threads", "read")`
- **路径解析**: 使用 `Paths.resolve_virtual_path()` 将虚拟路径（如 `/mnt/user-data/outputs/cat.png`）映射到实际文件系统路径
- **响应**: `FileResponse`（流式返回图片二进制）

## 实现文件

### `backend/app/gateway/routers/image_files.py`

```python
"""Image file serving router for viewed images.

Provides authenticated access to images stored in thread sandboxes,
allowing LLMs to reference images by URL instead of inline base64.
"""

import logging
import os
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.gateway.authz import require_auth, require_permission
from deerflow.config.paths import get_paths

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/threads/{thread_id}/files/image", tags=["files"])


@router.get("/{path:path}")
@require_auth
@require_permission("threads", "read")
async def get_image_file(
    request: Request,
    thread_id: str,
    path: str,
) -> FileResponse:
    """Serve an image file from the thread's sandbox.

    Args:
        thread_id: Thread ID for sandbox isolation.
        path: Virtual path relative to /mnt/user-data (e.g. outputs/cat.png).

    Returns:
        FileResponse streaming the image file.
    """
    # URL-decode the path
    decoded_path = unquote(path)
    virtual_path = f"/mnt/user-data/{decoded_path.lstrip('/')}"

    try:
        paths = get_paths()
        actual_path = paths.resolve_virtual_path(thread_id, virtual_path)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    if not actual_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {virtual_path}")

    if not actual_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Validate it's an image file by extension
    valid_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    if actual_path.suffix.lower() not in valid_extensions:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    return FileResponse(
        path=actual_path,
        media_type=None,  # FastAPI guesses from file extension
        filename=actual_path.name,
    )
```

### 路由注册

在 `backend/app/gateway/app.py` 中加入：
```python
from app.gateway.routers import image_files
...
app.include_router(image_files.router)
```

在 `backend/app/gateway/routers/__init__.py` 中加入：
```python
from . import image_files
__all__ = [..., "image_files"]
```

## 设计决策

1. **路径包含 thread_id**: 利用现有 sandbox 隔离机制，防止跨 thread 访问
2. **使用虚拟路径**: URL 中的 path 是相对于 `/mnt/user-data` 的，与 agent 内部使用的路径一致
3. **权限复用**: 复用 `threads:read` 权限，因为能查看 thread 的用户自然能查看其图片
4. **URL 编码**: 路径中可能包含中文或特殊字符，使用 `urllib.parse.unquote` 解码
