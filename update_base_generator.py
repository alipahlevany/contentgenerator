from pathlib import Path

path = Path("contents/core_services/generators/base.py")

path.write_text(
'''from abc import ABC, abstractmethod


class GeneratorOutputError(ValueError):
    """Raised when generated output does not satisfy generator rules."""


class BaseGenerator(ABC):

    @abstractmethod
    def get_pool_log_message(self, **kwargs):
        """
        Return a descriptive log message for the selected generation pool.
        """
        raise NotImplementedError

    @abstractmethod
    def select_generation_context(self, **kwargs):
        """
        Select all datasets required for one generation cycle.
        """
        raise NotImplementedError

    @abstractmethod
    def build_prompt_data(
        self,
        app_settings,
        language,
        topic,
        audience,
        goal,
        prompt_template,
        selected_rules,
    ):
        """
        Build prompts and metadata required for generation.
        """
        raise NotImplementedError

    @abstractmethod
    def extract_output(
        self,
        generated_text,
        fallback_title,
    ):
        """
        Extract final title and body from generated output.
        """
        raise NotImplementedError
''',
    encoding="utf-8",
)

print("OK: BaseGenerator updated.")
