from pathlib import Path

path = Path("contents/core_services/generators/email_reply.py")

text = path.read_text(encoding="utf-8")

if "def get_pool_log_message" in text:
    print("Already updated.")
    raise SystemExit

insert = '''
    def get_pool_log_message(
        self,
        languages,
        **kwargs,
    ):
        return (
            "Using email reply generation pool. "
            f"Languages: {len(languages)}."
        )

    def select_generation_context(
        self,
        *,
        languages,
        random_module,
        **kwargs,
    ):
        return {
            "language": random_module.choice(languages),
            "topic": None,
            "audience": None,
            "goal": None,
            "prompt_template": None,
            "selected_rules": [],
        }

'''

marker = "class EmailReplyGenerator(BaseGenerator):\n"
text = text.replace(marker, marker + insert)

path.write_text(text, encoding="utf-8")

print("OK: EmailReplyGenerator updated.")
