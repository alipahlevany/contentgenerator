#!/usr/bin/env bash

set -euo pipefail

# مسیر پروژه را اینجا وارد کن یا هنگام اجرا به‌عنوان آرگومان بده
REPO_DIR="${1:-$(pwd)}"
TASK_FILE="$REPO_DIR/contents/tasks.py"
BRANCH="refactor/safe-api-architecture"

echo "Project directory: $REPO_DIR"

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "ERROR: This directory is not a Git repository:"
    echo "$REPO_DIR"
    exit 1
fi

cd "$REPO_DIR"

CURRENT_BRANCH="$(git branch --show-current)"

if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    echo "ERROR: Current branch is '$CURRENT_BRANCH'"
    echo "Expected branch: '$BRANCH'"
    exit 1
fi

if [ ! -f "$TASK_FILE" ]; then
    echo "ERROR: File not found:"
    echo "$TASK_FILE"
    exit 1
fi

if grep -A12 '@shared_task(' "$TASK_FILE" | grep -q 'queue="delivery"'; then
    echo "Task is already configured for the delivery queue."
else
    python3 - "$TASK_FILE" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

pattern = re.compile(
    r'(@shared_task\(\s*'
    r'bind=True,\s*)'
    r'(?=autoretry_for=\(RetryableDeliveryError,\),)',
    re.MULTILINE,
)

replacement = (
    r'\1'
    'queue="delivery",\n'
    '    routing_key="delivery",\n'
    '    '
)

updated, count = pattern.subn(replacement, text, count=1)

if count != 1:
    raise SystemExit(
        "ERROR: Could not safely find the deliver_content_callback decorator."
    )

path.write_text(updated, encoding="utf-8")
print("contents/tasks.py updated successfully.")
PY
fi

echo
echo "Checking changed section:"
grep -n -A14 -B2 'queue="delivery"' contents/tasks.py

echo
echo "Running Django check..."

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

python manage.py check

echo
echo "Git diff:"
git diff -- contents/tasks.py

if git diff --quiet -- contents/tasks.py; then
    echo "No new code changes to commit."
    exit 0
fi

git add contents/tasks.py
git commit -m "Bind content delivery task to delivery queue"
git push origin "$BRANCH"

echo
echo "Done."
echo "Now run git pull and restart Celery only on the Generator production server."
