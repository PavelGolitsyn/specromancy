DEFAULT_WIDTH = 88


def output_width(configured: int | None) -> int:
    return DEFAULT_WIDTH if configured is None else configured
