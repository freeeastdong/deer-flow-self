#!/bin/bash
# =============================================================================
# 视频生成异步化重构 - Phase 备份脚本
# =============================================================================
# 用法: ./backup-phase.sh <phase_name>
# 示例: ./backup-phase.sh phase1
# =============================================================================

set -euo pipefail

PHASE=${1:-"unknown_phase"}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_ROOT=".backups/video-generation-async"
BACKUP_DIR="${BACKUP_ROOT}/${PHASE}_${TIMESTAMP}"

# 项目根目录（脚本在 docs/video-generation-async-refactor/scripts/ 下）
PROJECT_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "${PROJECT_ROOT}"

mkdir -p "${BACKUP_DIR}"

echo "======================================"
echo "  Video Generation Async Refactor"
echo "  Phase Backup: ${PHASE}"
echo "  Timestamp: ${TIMESTAMP}"
echo "======================================"
echo ""

# 定义需要备份的文件列表
FILES_TO_BACKUP=(
    # Phase 1-3 可能修改的文件
    "backend/app/gateway/app.py"
    "backend/app/gateway/routers/__init__.py"
    
    # Phase 4 修改的文件
    "skills/public/video-generation/scripts/generate.py"
    "skills/public/video-generation/SKILL.md"
    
    # Phase 6 修改的文件
    "frontend/src/components/workspace/chats/chat-box.tsx"
    "frontend/src/components/workspace/artifacts/artifact-file-list.tsx"
    "frontend/src/components/workspace/artifacts/artifact-file-detail.tsx"
    
    # 配置文件
    "config.yaml"
    "config.example.yaml"
)

# 备份存在的文件
for file in "${FILES_TO_BACKUP[@]}"; do
    if [ -f "$file" ]; then
        target_dir="${BACKUP_DIR}/$(dirname "$file")"
        mkdir -p "${target_dir}"
        cp "$file" "${target_dir}/"
        echo "  [BACKUP] $file"
    fi
done

# 如果已有新增文件，也一并备份（通过 git status 检测）
echo ""
echo "  Detecting new files from git..."
git status --short | grep "^??" | awk '{print $2}' | while read -r new_file; do
    # 只备份本项目相关的新增文件
    if [[ "$new_file" == backend/* ]] || [[ "$new_file" == frontend/* ]] || [[ "$new_file" == skills/* ]]; then
        target_dir="${BACKUP_DIR}/$(dirname "$new_file")"
        mkdir -p "${target_dir}"
        cp "$new_file" "${target_dir}/"
        echo "  [BACKUP-NEW] $new_file"
    fi
done

# 保存 git diff（已追踪文件的改动）
echo ""
echo "  Saving git diff..."
git diff > "${BACKUP_DIR}/git-diff.patch" 2>/dev/null || true
git diff --staged > "${BACKUP_DIR}/git-diff-staged.patch" 2>/dev/null || true

# 保存当前 git commit hash
git rev-parse HEAD > "${BACKUP_DIR}/git-head.txt" 2>/dev/null || echo "unknown" > "${BACKUP_DIR}/git-head.txt"

# 生成回退脚本
cat > "${BACKUP_DIR}/rollback.sh" << 'EOF'
#!/bin/bash
# 自动生成的回退脚本
# 用法: cd 项目根目录 && bash .backups/video-generation-async/<phase_timestamp>/rollback.sh

set -euo pipefail

BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${BACKUP_DIR}/../../.." && pwd)"
cd "${PROJECT_ROOT}"

echo "Rolling back from: ${BACKUP_DIR}"
echo ""

# 恢复已追踪的文件
find "${BACKUP_DIR}" -type f | while read -r backup_file; do
    rel_path="${backup_file#${BACKUP_DIR}/}"
    
    # 跳过元数据文件
    [[ "$rel_path" == "git-diff.patch" ]] && continue
    [[ "$rel_path" == "git-diff-staged.patch" ]] && continue
    [[ "$rel_path" == "git-head.txt" ]] && continue
    [[ "$rel_path" == "rollback.sh" ]] && continue
    
    if [ -f "$rel_path" ]; then
        cp "${backup_file}" "${rel_path}"
        echo "  [RESTORED] ${rel_path}"
    fi
done

echo ""
echo "Rollback completed."
echo "Note: New files created during the phase are NOT deleted by this script."
echo "      Please delete them manually if needed."
EOF

chmod +x "${BACKUP_DIR}/rollback.sh"

echo ""
echo "======================================"
echo "  Backup completed successfully!"
echo "  Location: ${BACKUP_DIR}"
echo "======================================"
echo ""
echo "  To rollback, run:"
echo "    bash ${BACKUP_DIR}/rollback.sh"
echo ""
