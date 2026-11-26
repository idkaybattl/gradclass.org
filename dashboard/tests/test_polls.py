from datetime import timedelta

from django.core import signing
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import (
    OPTION_LABEL_MAX_LENGTH,
    BallotVote,
    Option,
    Poll,
    Question,
    QuestionParticipation,
)
from ..services import BALLOT_SALT, ballot_cookie_name, cast_poll_vote
from .helpers import User, make_rep


class PollTestCase(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="student", password="password")
        self.other = User.objects.create_user(username="other", password="password")
        self.rep = make_rep("rep")
        for user in (self.student, self.other, self.rep):
            user.profile.has_had_introduction = True
            user.profile.save(update_fields=["has_had_introduction"])

    def make_poll(
        self,
        *,
        creator=None,
        mode=Poll.Mode.FIXED,
        phase=Poll.Phase.DRAFT,
        results_public=True,
        suggestions_public=True,
        title="Abimotto",
        approved=("A", "B"),
        suggested=(),
    ):
        now = timezone.now()
        poll = Poll.objects.create(
            title=title,
            description="",
            creator=creator or self.rep,
            mode=mode,
            results_public=results_public,
            suggestions_public=suggestions_public,
            suggestion_deadline=now + timedelta(days=10),
            voting_deadline=now + timedelta(days=20),
        )
        question = Question.objects.create(poll=poll, prompt=poll.title)

        if phase != Poll.Phase.DRAFT:
            poll.published_at = now - timedelta(days=1)
        if phase in {Poll.Phase.MODERATION, Poll.Phase.VOTING, Poll.Phase.CLOSED}:
            poll.suggestion_deadline = now - timedelta(days=1)
        if phase in {Poll.Phase.VOTING, Poll.Phase.CLOSED}:
            poll.voting_started_at = now - timedelta(hours=1)
            poll.voting_deadline = now + timedelta(days=1)
        if phase == Poll.Phase.CLOSED:
            poll.voting_deadline = now - timedelta(minutes=1)
        poll.save()

        for index, label in enumerate(approved):
            Option.objects.create(
                question=question,
                label=label,
                order=index,
                state=Option.State.APPROVED,
            )
        for index, label in enumerate(suggested):
            Option.objects.create(
                question=question,
                label=label,
                order=len(approved) + index,
                state=Option.State.SUGGESTED,
                created_by=self.student,
            )

        return poll

    def htmx(self):
        return {"HTTP_HX_REQUEST": "true"}

    def options(self, poll):
        return list(poll.questions.first().options.all())


class PollListViewTests(PollTestCase):
    def test_list_requires_login(self):
        response = self.client.get(reverse("polls"))

        self.assertEqual(response.status_code, 302)

    def test_list_shows_open_polls_to_students(self):
        poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS)
        self.client.force_login(self.student)

        response = self.client.get(reverse("polls"))

        self.assertContains(response, poll.title)
        self.assertNotContains(response, "Entwürfe")

    def test_drafts_are_manager_only(self):
        draft = self.make_poll(phase=Poll.Phase.DRAFT)
        self.client.force_login(self.student)

        response = self.client.get(reverse("polls"), {"filter": "drafts"})

        self.assertNotContains(response, draft.title)
        self.assertNotContains(response, "Entwürfe")

        self.client.force_login(self.rep)
        response = self.client.get(reverse("polls"), {"filter": "drafts"})

        self.assertContains(response, draft.title)

    def test_list_renders_all_phases_for_client_filtering(self):
        open_poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS, title="Offene Umfrage")
        closed_poll = self.make_poll(phase=Poll.Phase.CLOSED, title="Beendete Umfrage")
        self.client.force_login(self.student)

        response = self.client.get(reverse("polls"))

        self.assertContains(response, open_poll.title)
        self.assertContains(response, closed_poll.title)
        self.assertContains(response, 'data-polls-filter="closed"')

    def test_draft_detail_is_hidden_from_students(self):
        draft = self.make_poll(phase=Poll.Phase.DRAFT)
        self.client.force_login(self.student)

        response = self.client.get(reverse("poll-details", args=[draft.pk]))

        self.assertEqual(response.status_code, 404)


class PollCreateAndEditTests(PollTestCase):
    def payload(self, **overrides):
        data = {
            "title": "Abimotto 2028",
            "description": "",
            "mode": Poll.Mode.FIXED,
            "suggestions_public": "on",
            "results_public": "on",
            "suggestion_deadline": "",
            "voting_deadline": (timezone.localtime() + timedelta(days=10)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "options": "Motto A\nMotto B",
        }
        data.update(overrides)
        return data

    def test_students_cannot_create_polls(self):
        self.client.force_login(self.student)

        response = self.client.post(reverse("poll-create"), self.payload())

        self.assertEqual(response.status_code, 302)
        self.assertIn("poll-create-denied", response.url)
        self.assertFalse(Poll.objects.exists())

    def test_rep_creates_poll_with_question_and_options(self):
        self.client.force_login(self.rep)

        response = self.client.post(reverse("poll-create"), self.payload())

        poll = Poll.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(poll.title, "Abimotto 2028")
        self.assertEqual(poll.questions.first().prompt, poll.title)
        self.assertEqual(
            list(poll.questions.first().options.values_list("label", flat=True)),
            ["Motto A", "Motto B"],
        )

    def test_create_suggestion_mode_without_voting_deadline(self):
        self.client.force_login(self.rep)
        suggestion_deadline = (timezone.localtime() + timedelta(days=3)).strftime(
            "%Y-%m-%dT%H:%M"
        )

        response = self.client.post(
            reverse("poll-create"),
            self.payload(
                mode=Poll.Mode.SUGGESTIONS,
                options="",
                suggestion_deadline=suggestion_deadline,
                voting_deadline="",
            ),
        )

        poll = Poll.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(poll.voting_deadline)

    def test_fixed_poll_requires_voting_deadline(self):
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("poll-create"), self.payload(voting_deadline="")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bitte eine Abstimmungsfrist angeben.")
        self.assertFalse(Poll.objects.exists())

    def test_create_requires_two_options(self):
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("poll-create"), self.payload(options="Nur eine")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mindestens zwei Optionen")
        self.assertFalse(Poll.objects.exists())

    def test_create_with_suggestions_requires_suggestion_deadline(self):
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("poll-create"),
            self.payload(
                mode=Poll.Mode.SUGGESTIONS,
                options="",
                suggestion_deadline="",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vorschlagsfrist angeben")

    def test_creator_manages_own_poll_without_capability(self):
        poll = self.make_poll(creator=self.student, phase=Poll.Phase.DRAFT)
        self.client.force_login(self.student)

        response = self.client.get(reverse("poll-edit", args=[poll.pk]), **self.htmx())
        self.assertEqual(response.status_code, 200)

        poll = self.make_poll(
            creator=self.student,
            phase=Poll.Phase.MODERATION,
            mode=Poll.Mode.SUGGESTIONS,
            approved=(),
            suggested=("Idee",),
        )
        option = self.options(poll)[0]
        self.client.post(
            reverse("poll-moderate", args=[poll.pk]),
            {"action": "approve", "option": option.pk},
        )
        option.refresh_from_db()
        self.assertEqual(option.state, Option.State.APPROVED)

    def test_edit_is_draft_only(self):
        poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS, mode=Poll.Mode.SUGGESTIONS)
        self.client.force_login(self.rep)

        response = self.client.get(reverse("poll-edit", args=[poll.pk]))

        self.assertIn("poll-not-draft", response.url)

    def test_edit_updates_draft_options(self):
        poll = self.make_poll(phase=Poll.Phase.DRAFT)
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("poll-edit", args=[poll.pk]),
            self.payload(title="Neues Motto", options="C\nD"),
        )

        poll.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(poll.title, "Neues Motto")
        self.assertEqual(
            list(poll.questions.first().options.values_list("label", flat=True)),
            ["C", "D"],
        )

    def test_create_and_edit_render_htmx_partials(self):
        self.client.force_login(self.rep)

        create = self.client.get(reverse("poll-create"), **self.htmx())
        self.assertEqual(create.status_code, 200)
        self.assertNotContains(create, "<html")

        poll = self.make_poll(phase=Poll.Phase.DRAFT)
        edit = self.client.get(reverse("poll-edit", args=[poll.pk]), **self.htmx())
        self.assertEqual(edit.status_code, 200)
        self.assertNotContains(edit, "<html")


class PollPhaseTests(PollTestCase):
    def test_students_cannot_change_phases(self):
        poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS)
        self.client.force_login(self.student)

        response = self.client.post(reverse("poll-close-suggestions", args=[poll.pk]))

        poll.refresh_from_db()
        self.assertIn("moderation-denied", response.url)
        self.assertIsNone(poll.suggestions_closed_at)

    def test_start_and_close_suggestions_early(self):
        poll = self.make_poll(phase=Poll.Phase.DRAFT, mode=Poll.Mode.SUGGESTIONS)
        self.client.force_login(self.rep)

        self.client.post(reverse("poll-start-suggestions", args=[poll.pk]))
        poll.refresh_from_db()
        self.assertEqual(poll.phase, Poll.Phase.SUGGESTIONS)

        self.client.post(reverse("poll-close-suggestions", args=[poll.pk]))
        poll.refresh_from_db()
        self.assertEqual(poll.phase, Poll.Phase.MODERATION)

    def test_start_voting_prompts_for_missing_deadline(self):
        poll = self.make_poll(phase=Poll.Phase.DRAFT)
        poll.voting_deadline = None
        poll.save(update_fields=["voting_deadline"])
        self.client.force_login(self.rep)

        response = self.client.post(reverse("poll-start-voting", args=[poll.pk]))

        poll.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Abstimmungsfrist festlegen")
        self.assertIsNone(poll.voting_started_at)

    def test_start_voting_with_deadline_starts_immediately(self):
        poll = self.make_poll(phase=Poll.Phase.DRAFT)
        poll.voting_deadline = None
        poll.save(update_fields=["voting_deadline"])
        deadline = (timezone.localtime() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("poll-start-voting", args=[poll.pk]),
            {"voting_deadline": deadline},
        )

        poll.refresh_from_db()
        self.assertIn("voting-started", response.url)
        self.assertEqual(poll.phase, Poll.Phase.VOTING)
        self.assertIsNotNone(poll.voting_deadline)

    def test_start_voting_needs_two_approved_options(self):
        poll = self.make_poll(phase=Poll.Phase.DRAFT, approved=("A",))
        self.client.force_login(self.rep)

        response = self.client.post(reverse("poll-start-voting", args=[poll.pk]))

        poll.refresh_from_db()
        self.assertIn("poll-phase-denied", response.url)
        self.assertEqual(poll.phase, Poll.Phase.DRAFT)

    def test_voting_cannot_start_before_suggestions_end(self):
        poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS, mode=Poll.Mode.SUGGESTIONS)
        self.client.force_login(self.rep)

        response = self.client.post(reverse("poll-start-voting", args=[poll.pk]))

        poll.refresh_from_db()
        self.assertIn("poll-phase-denied", response.url)
        self.assertEqual(poll.phase, Poll.Phase.SUGGESTIONS)

    def test_close_voting_early_shows_results(self):
        poll = self.make_poll(phase=Poll.Phase.VOTING)
        cast_poll_vote(poll.questions.first(), self.options(poll)[0], self.student)
        self.client.force_login(self.rep)

        response = self.client.post(reverse("poll-close-voting", args=[poll.pk]))

        poll.refresh_from_db()
        self.assertEqual(poll.phase, Poll.Phase.CLOSED)
        self.assertIn("voting-closed", response.url)

        detail = self.client.get(reverse("poll-details", args=[poll.pk]))
        self.assertContains(detail, "100 %")

    def test_manager_can_change_suggestion_deadline(self):
        poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS, mode=Poll.Mode.SUGGESTIONS)
        old_deadline = poll.suggestion_deadline
        deadline = (timezone.localtime() + timedelta(days=15)).strftime(
            "%Y-%m-%dT%H:%M"
        )
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("poll-suggestion-deadline", args=[poll.pk]),
            {"suggestion_deadline": deadline},
        )

        poll.refresh_from_db()
        self.assertIn("suggestion-deadline-updated", response.url)
        self.assertGreater(poll.suggestion_deadline, old_deadline)
        self.assertEqual(poll.phase, Poll.Phase.SUGGESTIONS)

    def test_manager_can_shorten_suggestion_deadline(self):
        poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS, mode=Poll.Mode.SUGGESTIONS)
        old_deadline = poll.suggestion_deadline
        deadline = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("poll-suggestion-deadline", args=[poll.pk]),
            {"suggestion_deadline": deadline},
        )

        poll.refresh_from_db()
        self.assertIn("suggestion-deadline-updated", response.url)
        self.assertLess(poll.suggestion_deadline, old_deadline)
        self.assertEqual(poll.phase, Poll.Phase.SUGGESTIONS)

    def test_suggestion_deadline_must_be_in_the_future(self):
        poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS, mode=Poll.Mode.SUGGESTIONS)
        old_deadline = poll.suggestion_deadline
        deadline = (timezone.localtime() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        self.client.force_login(self.rep)

        response = self.client.post(
            reverse("poll-suggestion-deadline", args=[poll.pk]),
            {"suggestion_deadline": deadline},
        )

        poll.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "in der Zukunft liegen")
        self.assertEqual(poll.suggestion_deadline, old_deadline)

    def test_students_cannot_change_suggestion_deadline(self):
        poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS, mode=Poll.Mode.SUGGESTIONS)
        old_deadline = poll.suggestion_deadline
        deadline = (timezone.localtime() + timedelta(days=15)).strftime(
            "%Y-%m-%dT%H:%M"
        )
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("poll-suggestion-deadline", args=[poll.pk]),
            {"suggestion_deadline": deadline},
        )

        poll.refresh_from_db()
        self.assertIn("moderation-denied", response.url)
        self.assertEqual(poll.suggestion_deadline, old_deadline)


class PollSuggestionTests(PollTestCase):
    def test_student_can_add_suggestions_up_to_three(self):
        poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS, mode=Poll.Mode.SUGGESTIONS)
        self.client.force_login(self.student)

        for index in range(3):
            response = self.client.post(
                reverse("poll-suggest", args=[poll.pk]),
                {"action": "add", "label": f"Idee {index}"},
            )
            self.assertEqual(response.status_code, 302)

        self.assertEqual(
            poll.questions.first().options.filter(created_by=self.student).count(), 3
        )

        response = self.client.post(
            reverse("poll-suggest", args=[poll.pk]),
            {"action": "add", "label": "Idee 4"},
        )
        self.assertContains(response, "höchstens 3 Vorschläge", status_code=200)
        self.assertEqual(
            poll.questions.first().options.filter(created_by=self.student).count(), 3
        )

    def test_suggestion_limit_comes_from_the_poll(self):
        poll = self.make_poll(
            phase=Poll.Phase.SUGGESTIONS,
            mode=Poll.Mode.SUGGESTIONS,
            approved=(),
        )
        poll.max_suggestions_per_user = 1
        poll.save(update_fields=["max_suggestions_per_user"])
        self.client.force_login(self.student)

        self.client.post(
            reverse("poll-suggest", args=[poll.pk]),
            {"action": "add", "label": "Eins"},
        )
        response = self.client.post(
            reverse("poll-suggest", args=[poll.pk]),
            {"action": "add", "label": "Zwei"},
        )

        self.assertContains(response, "höchstens 1 Vorschläge", status_code=200)
        self.assertEqual(
            poll.questions.first().options.filter(created_by=self.student).count(),
            1,
        )

    def test_new_suggestions_are_approved_by_default(self):
        poll = self.make_poll(
            phase=Poll.Phase.SUGGESTIONS,
            mode=Poll.Mode.SUGGESTIONS,
            approved=(),
        )
        self.client.force_login(self.student)

        self.client.post(
            reverse("poll-suggest", args=[poll.pk]),
            {"action": "add", "label": "Idee"},
        )

        option = poll.questions.first().options.get(label="Idee")
        self.assertEqual(option.state, Option.State.APPROVED)

    def test_suggestion_authors_are_manager_only(self):
        poll = self.make_poll(
            phase=Poll.Phase.SUGGESTIONS,
            mode=Poll.Mode.SUGGESTIONS,
            approved=(),
            suggested=("Idee",),
        )
        detail_url = reverse("poll-details", args=[poll.pk])
        moderation_url = reverse("poll-moderate", args=[poll.pk])

        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(detail_url), "student")
        self.assertEqual(self.client.get(moderation_url).status_code, 302)

        self.client.force_login(self.rep)
        self.assertContains(self.client.get(detail_url), "student")
        self.assertContains(self.client.get(moderation_url, **self.htmx()), "student")

    def test_suggestions_public_toggle_hides_them_from_students(self):
        poll = self.make_poll(
            phase=Poll.Phase.SUGGESTIONS,
            mode=Poll.Mode.SUGGESTIONS,
            approved=(),
            suggested=("Geheim",),
            suggestions_public=False,
        )
        url = reverse("poll-details", args=[poll.pk])

        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(url), "Geheim")

        self.client.force_login(self.rep)
        self.assertContains(self.client.get(url), "Geheim")

    def test_own_suggestion_can_be_edited_and_withdrawn(self):
        poll = self.make_poll(
            phase=Poll.Phase.SUGGESTIONS,
            mode=Poll.Mode.SUGGESTIONS,
            approved=(),
            suggested=("Alt",),
        )
        option = poll.questions.first().options.get(label="Alt")
        self.client.force_login(self.student)

        self.client.post(
            reverse("poll-suggest", args=[poll.pk]),
            {"action": "edit", "option": option.pk, "label": "Neu"},
        )
        option.refresh_from_db()
        self.assertEqual(option.label, "Neu")

        self.client.post(
            reverse("poll-suggest", args=[poll.pk]),
            {"action": "withdraw", "option": option.pk},
        )
        self.assertFalse(Option.objects.filter(pk=option.pk).exists())

    def test_moderation_merges_and_rejects(self):
        poll = self.make_poll(
            phase=Poll.Phase.MODERATION,
            mode=Poll.Mode.SUGGESTIONS,
            approved=(),
            suggested=("Eins", "Zwei"),
        )
        first, second = self.options(poll)
        self.client.force_login(self.rep)

        self.client.post(
            reverse("poll-moderate", args=[poll.pk]),
            {"action": "merge", "option": second.pk, "merged_into": first.pk},
            **self.htmx(),
        )
        second.refresh_from_db()
        self.assertEqual(second.state, Option.State.MERGED)
        self.assertEqual(second.merged_into_id, first.pk)

        panel = self.client.get(reverse("poll-moderate", args=[poll.pk]), **self.htmx())
        self.assertContains(panel, "Zusammengeführt:")
        self.assertContains(panel, "Zwei")
        self.assertContains(panel, "von student")

        self.client.post(
            reverse("poll-moderate", args=[poll.pk]),
            {"action": "reject", "option": first.pk},
            **self.htmx(),
        )
        first.refresh_from_db()
        self.assertEqual(first.state, Option.State.REJECTED)

        detail = self.client.get(reverse("poll-details", args=[poll.pk]))
        self.assertNotContains(detail, "Eins")

        self.client.post(
            reverse("poll-moderate", args=[poll.pk]),
            {"action": "approve", "option": first.pk},
            **self.htmx(),
        )
        first.refresh_from_db()
        self.assertEqual(first.state, Option.State.APPROVED)

    def test_options_cannot_be_moderated_after_voting_starts(self):
        poll = self.make_poll(phase=Poll.Phase.VOTING, suggested=())
        option = self.options(poll)[0]
        self.client.force_login(self.rep)

        self.client.post(
            reverse("poll-moderate", args=[poll.pk]),
            {"action": "reject", "option": option.pk},
        )

        self.assertTrue(Option.objects.filter(pk=option.pk).exists())

    def test_students_cannot_moderate(self):
        poll = self.make_poll(
            phase=Poll.Phase.SUGGESTIONS,
            mode=Poll.Mode.SUGGESTIONS,
            approved=(),
            suggested=("Idee",),
        )
        option = self.options(poll)[0]
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("poll-moderate", args=[poll.pk]),
            {"action": "approve", "option": option.pk},
        )

        option.refresh_from_db()
        self.assertIn("moderation-denied", response.url)
        self.assertEqual(option.state, Option.State.SUGGESTED)


class PollVotingTests(PollTestCase):
    def test_student_votes_and_changes_their_vote(self):
        poll = self.make_poll(phase=Poll.Phase.VOTING)
        first, second = self.options(poll)
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("poll-vote", args=[poll.pk]), {"option": first.pk}
        )
        self.assertIn("voted", response.url)
        self.assertTrue(
            QuestionParticipation.objects.filter(
                question=poll.questions.first(), user=self.student
            ).exists()
        )
        self.assertEqual(BallotVote.objects.get().option_id, first.pk)

        response = self.client.post(
            reverse("poll-vote", args=[poll.pk]), {"option": second.pk}
        )
        self.assertIn("vote-changed", response.url)
        self.assertEqual(BallotVote.objects.count(), 1)
        self.assertEqual(BallotVote.objects.get().option_id, second.pk)

    def test_vote_without_ballot_cookie_is_rejected(self):
        poll = self.make_poll(phase=Poll.Phase.VOTING)
        options = self.options(poll)
        cast_poll_vote(poll.questions.first(), options[0], self.student)
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("poll-vote", args=[poll.pk]), {"option": options[1].pk}
        )

        self.assertIn("ballot-lost", response.url)
        self.assertEqual(BallotVote.objects.get().option_id, options[0].pk)

    def test_vote_with_foreign_cookie_is_rejected(self):
        poll = self.make_poll(phase=Poll.Phase.VOTING)
        options = self.options(poll)
        cast_poll_vote(poll.questions.first(), options[0], self.student)
        _, other_token = cast_poll_vote(poll.questions.first(), options[1], self.other)

        self.client.force_login(self.student)
        self.client.cookies[ballot_cookie_name(poll.questions.first())] = signing.dumps(
            other_token, salt=BALLOT_SALT
        )

        response = self.client.post(
            reverse("poll-vote", args=[poll.pk]), {"option": options[1].pk}
        )

        self.assertIn("ballot-lost", response.url)
        self.assertEqual(BallotVote.objects.filter(option=options[0]).count(), 1)
        self.assertEqual(BallotVote.objects.filter(option=options[1]).count(), 1)

    def test_vote_after_close_is_rejected(self):
        poll = self.make_poll(phase=Poll.Phase.CLOSED)
        option = self.options(poll)[0]
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("poll-vote", args=[poll.pk]), {"option": option.pk}
        )

        self.assertIn("vote-closed", response.url)
        self.assertFalse(QuestionParticipation.objects.exists())

    def test_option_must_belong_to_the_question(self):
        poll = self.make_poll(phase=Poll.Phase.VOTING)
        other_poll = self.make_poll(phase=Poll.Phase.VOTING)
        option = self.options(other_poll)[0]
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("poll-vote", args=[poll.pk]), {"option": option.pk}
        )

        self.assertIn("vote-invalid", response.url)
        self.assertFalse(BallotVote.objects.exists())


class PollResultTests(PollTestCase):
    def test_results_are_live_and_show_percent_and_fraction(self):
        poll = self.make_poll(phase=Poll.Phase.VOTING)
        first, _second = self.options(poll)
        cast_poll_vote(poll.questions.first(), first, self.student)
        cast_poll_vote(poll.questions.first(), first, self.other)

        self.client.force_login(self.student)
        response = self.client.get(reverse("poll-details", args=[poll.pk]))

        self.assertContains(response, "100 %")
        self.assertContains(response, "2/2")

    def test_tie_renders_gleichstand(self):
        poll = self.make_poll(phase=Poll.Phase.VOTING)
        first, second = self.options(poll)
        cast_poll_vote(poll.questions.first(), first, self.student)
        cast_poll_vote(poll.questions.first(), second, self.other)

        self.client.force_login(self.student)
        response = self.client.get(reverse("poll-details", args=[poll.pk]))

        self.assertContains(response, "Gleichstand")

    def test_internal_results_are_hidden_from_students(self):
        poll = self.make_poll(phase=Poll.Phase.CLOSED, results_public=False)
        cast_poll_vote(poll.questions.first(), self.options(poll)[0], self.other)
        self.client.force_login(self.student)

        detail = self.client.get(reverse("poll-details", args=[poll.pk]))
        self.assertContains(detail, "Ergebnisse dieser Umfrage sind intern")
        self.assertNotContains(detail, "100 %")

        results = self.client.get(reverse("poll-results", args=[poll.pk]))
        self.assertEqual(results.status_code, 403)

        self.client.force_login(self.rep)
        results = self.client.get(reverse("poll-results", args=[poll.pk]))
        self.assertEqual(results.status_code, 200)
        self.assertContains(results, "100 %")

    def test_results_endpoint_hides_nothing_when_public(self):
        poll = self.make_poll(phase=Poll.Phase.CLOSED)
        cast_poll_vote(poll.questions.first(), self.options(poll)[0], self.other)
        self.client.force_login(self.student)

        response = self.client.get(reverse("poll-results", args=[poll.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100 % · 1/1")


class PollLengthLimitTests(PollTestCase):
    def test_suggestion_label_length_is_enforced(self):
        poll = self.make_poll(phase=Poll.Phase.SUGGESTIONS, mode=Poll.Mode.SUGGESTIONS)
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("poll-suggest", args=[poll.pk]),
            {
                "action": "add",
                "label": "x" * (OPTION_LABEL_MAX_LENGTH + 1),
            },
        )

        self.assertContains(response, "Zeichen haben", status_code=200)
        self.assertEqual(
            poll.questions.first().options.filter(created_by=self.student).count(), 0
        )


class PollExportTests(PollTestCase):
    def test_export_requires_manager(self):
        poll = self.make_poll(
            phase=Poll.Phase.SUGGESTIONS,
            mode=Poll.Mode.SUGGESTIONS,
            approved=(),
            suggested=("Geheim",),
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("poll-export", args=[poll.pk]))

        self.assertEqual(response.status_code, 403)

    def test_export_lists_suggestions_with_authors(self):
        poll = self.make_poll(
            phase=Poll.Phase.SUGGESTIONS,
            mode=Poll.Mode.SUGGESTIONS,
            approved=("A",),
            suggested=("Geheim",),
        )
        self.client.force_login(self.rep)

        response = self.client.get(reverse("poll-export", args=[poll.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        content = response.content.decode()
        self.assertIn("Vorschlag;Autor:in;Status;Zusammengeführt in", content)
        self.assertIn("A;;Freigegeben;", content)
        self.assertIn("Geheim;student;Vorgeschlagen;", content)

    def test_creator_can_export_own_poll(self):
        poll = self.make_poll(
            creator=self.student,
            phase=Poll.Phase.SUGGESTIONS,
            mode=Poll.Mode.SUGGESTIONS,
            approved=(),
            suggested=("Geheim",),
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("poll-export", args=[poll.pk]))

        self.assertEqual(response.status_code, 200)
