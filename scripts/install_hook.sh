#!/bin/bash
# Cài git post-commit hook để tự động cập nhật CLAUDE.md và AGENTS.md.
# Chạy một lần: bash scripts/install_hook.sh
set -e
HOOK=".git/hooks/post-commit"
cat > "$HOOK" << 'HOOK_SCRIPT'
#!/bin/bash
# Tự động cập nhật CLAUDE.md và AGENTS.md sau mỗi commit vào main.
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if [ "$BRANCH" = "main" ]; then
  REPO_ROOT=$(git rev-parse --show-toplevel)
  SCRIPT="$REPO_ROOT/scripts/update_context.py"
  if [ -f "$SCRIPT" ]; then
    python3 "$SCRIPT" 2>/dev/null && \
      git add CLAUDE.md AGENTS.md 2>/dev/null && \
      git commit --amend --no-edit --quiet 2>/dev/null || true
  fi
fi
HOOK_SCRIPT
chmod +x "$HOOK"
echo "✅ Git hook đã cài tại $HOOK"
echo "   CLAUDE.md và AGENTS.md sẽ tự động cập nhật sau mỗi commit vào main."
