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
    "user-edit-denied": (
        "error",
        "Du bist nicht berechtigt, dieses Nutzerprofil zu bearbeiten.",
    ),
    "password-denied": (
        "error",
        "Du bist nicht berechtigt, dieses Passwort zu ändern.",
    ),
    "reset-link-denied": (
        "error",
        "Du bist nicht berechtigt, einen Reset-Link zu erzeugen.",
    ),
    "profile-updated": ("success", "Profil erfolgreich bearbeitet"),
    "password-updated": ("success", "Passwort erfolgreich geändert"),
    "intro-profile-saved": ("success", "Profil gespeichert"),
    "poll-created": ("success", "Umfrage erstellt."),
    "poll-updated": ("success", "Umfrage gespeichert."),
    "poll-create-denied": (
        "error",
        "Du bist nicht berechtigt, Umfragen zu erstellen.",
    ),
    "poll-edit-denied": (
        "error",
        "Du bist nicht berechtigt, diese Umfrage zu bearbeiten.",
    ),
    "poll-not-draft": ("error", "Nur Entwürfe können bearbeitet werden."),
    "poll-phase-denied": (
        "error",
        "Diese Aktion ist in dieser Phase nicht möglich.",
    ),
    "suggestions-started": ("success", "Vorschlagsphase gestartet."),
    "suggestions-ended": ("error", "Die Vorschlagsphase ist beendet."),
    "suggestions-closed": ("success", "Vorschläge geschlossen."),
    "suggestion-deadline-updated": ("success", "Vorschlagsfrist geändert."),
    "voting-started": ("success", "Abstimmung gestartet."),
    "voting-closed": ("success", "Abstimmung beendet."),
    "suggestion-added": ("success", "Vorschlag hinzugefügt."),
    "suggestion-updated": ("success", "Vorschlag gespeichert."),
    "suggestion-withdrawn": ("success", "Vorschlag zurückgezogen."),
    "suggestion-approved": ("success", "Vorschlag freigegeben."),
    "suggestion-rejected": ("success", "Vorschlag abgelehnt."),
    "suggestion-merged": ("success", "Vorschläge zusammengeführt."),
    "moderation-denied": (
        "error",
        "Du bist nicht berechtigt, diese Umfrage zu moderieren.",
    ),
    "vote-invalid": ("error", "Diese Option gehört nicht zur Umfrage."),
    "vote-closed": ("error", "Die Abstimmung ist beendet."),
    "voted": ("success", "Stimme abgegeben."),
    "vote-changed": ("success", "Stimme geändert."),
    "ballot-lost": (
        "error",
        "Deine Stimme kann nicht geändert werden: Der Stimmzettel fehlt in diesem Browser.",
    ),
    "abikasse-entry-created": ("success", "Eintrag hinzugefügt."),
    "abikasse-entry-updated": ("success", "Eintrag gespeichert."),
    "abikasse-entry-deleted": ("success", "Eintrag gelöscht."),
    "abikasse-settings-updated": ("success", "Einstellungen gespeichert."),
    "ticket-count-updated": ("success", "Personenzahl gespeichert."),
    "quote-created": ("success", "Zitat hinzugefügt."),
    "quote-deleted": ("success", "Zitat gelöscht."),
    "quote-delete-denied": (
        "error",
        "Du bist nicht berechtigt, dieses Zitat zu löschen.",
    ),
    "quote-reported": ("success", "Zitat gemeldet."),
    "quote-already-reported": ("info", "Du hast dieses Zitat bereits gemeldet."),
    "quote-report-denied": ("error", "Du kannst dein eigenes Zitat nicht melden."),
    "report-dismissed": ("success", "Meldung verworfen."),
    "report-dismiss-denied": (
        "error",
        "Du bist nicht berechtigt, Meldungen zu verwalten.",
    ),
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
