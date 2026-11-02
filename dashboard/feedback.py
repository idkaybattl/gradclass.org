"""Server-rendered feedback for app actions.

See "Feedback pattern" in AGENTS.md. Feedback is rendered into the same
container as the action, never queued through ``django.contrib.messages``.
"""

from django.shortcuts import render

STATUS_FEEDBACK = {
    "joined": ("success", "Du nimmst jetzt teil"),
    "requested": ("success", "Anfrage gesendet"),
    "already-requested": ("info", "Du hast bereits angefragt"),
    "already-participant": ("error", "Du nimmst an diesem Projekt bereits teil."),
    "not-participant": ("error", "Du nimmst an diesem Projekt nicht teil."),
    "final": ("error", "Dieses Projekt ist bereits abgeschlossen."),
    "past": ("error", "Das Projekt liegt in der Vergangenheit."),
    "left": ("success", "Teilnahme beendet."),
    "earnings": ("success", "Einnahmen gesetzt."),
    "earnings-received": ("success", "Einnahmenstatus aktualisiert."),
    "participation-times": ("success", "Arbeitszeiten gespeichert."),
    "request-accepted": ("success", "Anfrage angenommen."),
    "request-declined": ("success", "Anfrage abgelehnt."),
    "deleted": ("success", "Aktion gelöscht."),
    "created": ("success", "Aktion erfolgreich erstellt"),
    "updated": ("success", "Aktion erfolgreich bearbeitet"),
    "rate-limited": ("error", "Erstellungslimit erreicht"),
    "create-denied": ("error", "Du bist nicht berechtigt, diese Aktion zu erstellen."),
    "edit-denied": ("error", "Du bist nicht berechtigt, diese Aktion zu bearbeiten."),
    "delete-denied": ("error", "Du bist nicht berechtigt, diese Aktion zu löschen."),
}


def get_feedback(status, **extra):
    entry = STATUS_FEEDBACK.get(status)
    if entry is None:
        return None

    kind, title = entry
    feedback: dict[str, object] = {"kind": kind, "title": title, "message": ""}

    action_url = extra.pop("action_url", None)
    action_label = extra.pop("action_label", None)
    action_htmx = extra.pop("action_htmx", False)
    if action_url and "actions" not in extra:
        extra["actions"] = [
            {
                "label": action_label or "Weiter",
                "url": action_url,
                "htmx": action_htmx,
            }
        ]

    feedback.update(extra)
    return feedback


def render_feedback(request, feedback, *, status=200):
    return render(
        request,
        "components/_feedback.html",
        {"feedback": feedback},
        status=status,
    )
