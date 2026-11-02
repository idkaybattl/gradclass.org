from datetime import timedelta


def format_duration(value):
    """Format a timedelta as H:MM, the representation used in forms and lists."""
    if value is None:
        return ""

    total_seconds = int(value.total_seconds())
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{sign}{hours}:{minutes:02d}"


def split_duration(value):
    """Split a timedelta or H:MM string into (hours, minutes).

    Invalid input is preserved so a re-rendered form does not clear what the
    user typed; the form field validates it afterwards.
    """
    if isinstance(value, timedelta):
        value = format_duration(value)
    if value is None:
        return None, None

    hours, separator, minutes = str(value).strip().partition(":")
    if not separator:
        return None, None

    try:
        return int(hours), int(minutes)
    except ValueError:
        return hours, minutes
