def calculate_quality_score(
    success_count,
    skip_count,
    duplicate_count,
    blocked_count,
    error_count,
):
    total = success_count + skip_count + duplicate_count + blocked_count + error_count

    if total <= 0:
        return 100

    penalty = (
        skip_count * 1
        + duplicate_count * 2
        + blocked_count * 3
        + error_count * 2
    )

    score = 100 - ((penalty / total) * 100)

    return max(0, min(100, round(score, 2)))


def calculate_confidence(total_events):
    if total_events <= 0:
        return 0

    if total_events >= 100:
        return 100

    return round(total_events, 2)