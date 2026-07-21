from contents.core_services.generators.email_reply import EmailReplyGenerator
from contents.core_services.generators.standard import StandardGenerator


def get_generator(generation_type):
    generators = {
        "standard": StandardGenerator,
        "email_reply": EmailReplyGenerator,
    }

    generator_class = generators.get(generation_type)

    if generator_class is None:
        raise ValueError(
            f"Unsupported generation type: {generation_type}"
        )

    return generator_class()