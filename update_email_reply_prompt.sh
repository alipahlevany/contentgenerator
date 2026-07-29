#!/usr/bin/env bash

set -e

FILE="contents/core_services/generators/email_reply.py"
BACKUP="${FILE}.backup-$(date +%Y%m%d-%H%M%S)"

if [ ! -f "$FILE" ]; then
    echo "ERROR: File not found: $FILE"
    exit 1
fi

cp "$FILE" "$BACKUP"
echo "Backup created: $BACKUP"

python - <<'PY'
from pathlib import Path
import re
import sys

file_path = Path("contents/core_services/generators/email_reply.py")
text = file_path.read_text(encoding="utf-8")

new_system_prompt = '''system_prompt = """
You generate realistic, natural, and ready-to-send email replies.

The output must feel like it was written by a real person.
It must not sound robotic, overly formal, generic, or AI-generated.

Rules:

- Write only the email reply body.
- Do not write a subject line.
- Do not explain your answer.
- Do not add labels such as "Reply", "Response", or "Email".
- Use the requested language naturally and fluently.
- Match the normal writing style and level of formality of that language.
- Keep the reply professional, warm, clear, direct, and human.
- Avoid generic customer-service templates.
- Avoid unnecessary introductions and repeated courtesy phrases.
- Do not always begin by thanking the recipient.
- Adapt the reply to the situation instead of generating the same structure repeatedly.
- Do not invent facts, names, dates, deadlines, promises, links,
  order numbers, email addresses, phone numbers, or company information.
- Use placeholders only when they are truly necessary.
- Allowed placeholders:
  [[name]], [[first_name]], [[company]], [[email]], [[phone]],
  [[website]], [[link]], [[order_number]], [[date]]
- Never generate a placeholder outside the allowed list.
- Do not include a sender name or signature.
- Do not end with initials, a single letter, unfinished text,
  or an incomplete sentence.
- Keep the reply between 40 and 120 words.
- Prefer 2 to 4 short paragraphs.
- Vary the structure and wording between outputs.
- The result must be immediately usable without editing.
"""'''

new_user_prompt = '''user_prompt = f"""
Generate one natural email reply in {language.name}.

Requirements:
- Sound human and conversational.
- Be concise, useful, and specific.
- Avoid generic customer-service wording.
- Do not invent missing information.
- Use placeholders only when absolutely necessary.
- Do not add a signature or sender name.
- End with a complete sentence.
"""'''

system_pattern = re.compile(
    r'(?P<indent>^[ \t]*)system_prompt\s*=\s*(?:f)?"""[\s\S]*?"""',
    re.MULTILINE,
)

user_pattern = re.compile(
    r'(?P<indent>^[ \t]*)user_prompt\s*=\s*f"""[\s\S]*?"""',
    re.MULTILINE,
)

system_match = system_pattern.search(text)

if not system_match:
    print("ERROR: system_prompt block was not found.")
    sys.exit(1)

system_indent = system_match.group("indent")
indented_system_prompt = "\n".join(
    system_indent + line if line else line
    for line in new_system_prompt.splitlines()
)

text = (
    text[:system_match.start()]
    + indented_system_prompt
    + text[system_match.end():]
)

user_match = user_pattern.search(text)

if not user_match:
    print("ERROR: user_prompt block was not found.")
    sys.exit(1)

user_indent = user_match.group("indent")
indented_user_prompt = "\n".join(
    user_indent + line if line else line
    for line in new_user_prompt.splitlines()
)

text = (
    text[:user_match.start()]
    + indented_user_prompt
    + text[user_match.end():]
)

file_path.write_text(text, encoding="utf-8")

print("Email reply prompts updated successfully.")
PY

echo
echo "Running syntax checks..."

python -m py_compile "$FILE"
python manage.py check

echo
echo "Done."
echo "Updated file: $FILE"
echo "Backup file:  $BACKUP"
