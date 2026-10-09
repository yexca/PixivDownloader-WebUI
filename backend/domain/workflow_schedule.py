def effective_weekdays(value: object) -> list[int]:
    """Keep the scheduler's Python value semantics before a JSON/browser round trip."""
    days = value if isinstance(value, list) else []
    return sorted({int(day) for day in days if str(day).isdigit() and 1 <= int(day) <= 7})
