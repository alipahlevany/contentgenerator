from abc import ABC, abstractmethod


class GeneratorOutputError(ValueError):
    """Raised when generated output does not satisfy generator rules."""


class BaseGenerator(ABC):
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
