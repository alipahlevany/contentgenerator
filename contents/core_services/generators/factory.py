from .registry import get_generator_class


def get_generator(generation_type):
    """
    Return an initialized generator instance.
    """
    generator_class = get_generator_class(generation_type)
    return generator_class()
