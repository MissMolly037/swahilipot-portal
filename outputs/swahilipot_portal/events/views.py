from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db import models as db_models
from django.http import JsonResponse
from core.permissions import capability_required
from core.notify import notify_all, notify_user, notify_managers
from core.reports import excel_response, pdf_response
from .forms import EventForm
from .models import Event, EventAttendance, EventRegistration


@login_required
def event_list(request):
    now = timezone.now()
    upcoming = Event.objects.filter(end_date__gte=now).order_by("start_date")
    past = Event.objects.filter(end_date__lt=now).order_by("-start_date")
    return render(request, "events/list.html", {"upcoming": upcoming, "past": past})


@capability_required("can_manage_events")
def event_create(request):
    form = EventForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        event = form.save()
        notify_all(
            f"New event: {event.title}",
            f'A new event "{event.title}" has been scheduled at {event.location} on {event.start_date:%b %d, %Y}. Register now!',
            exclude_pk=request.user.pk,
            link=f"/events/{event.pk}/",
        )
        messages.success(request, "Event created.")
        return redirect("events:list")
    return render(request, "form.html", {"form": form, "title": "Create Event"})


@login_required
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    registered = EventRegistration.objects.filter(event=event, participant=request.user).exists()
    attended   = EventAttendance.objects.filter(event=event, participant=request.user).exists()
    return render(request, "events/detail.html", {
        "event": event,
        "registered": registered,
        "attended": attended,
        "portal_qr_url": event.get_portal_qr_url(request),
    })


@login_required
def register(request, pk):
    """
    Portal direct registration.
    1. Records the registration in the DB (for portal tracking).
    2. Redirects to the pre-filled Google Form so the response is also
       captured in Google Sheets with the event ID pre-filled.
    """
    event = get_object_or_404(Event, pk=pk)
    if event.is_past:
        messages.error(request, "This event has already ended. Registration is closed.")
        return redirect("events:detail", pk=pk)
    if event.is_full:
        messages.error(request, "Event capacity has been reached. Registration is closed.")
        return redirect("events:detail", pk=pk)

    _, created = EventRegistration.objects.get_or_create(event=event, participant=request.user)
    if created:
        notify_user(
            request.user,
            f"Registered for: {event.title}",
            f'Your registration for "{event.title}" on {event.start_date:%b %d, %Y} is confirmed.',
            link=f"/events/{event.pk}/",
        )
        notify_managers(
            f"New event registration: {event.title}",
            f'{request.user} registered for "{event.title}".',
            link=f"/events/{event.pk}/",
        )
        # Notify everyone if event just became full
        if event.is_full:
            notify_all(
                f"Event fully booked: {event.title}",
                f'"{event.title}" on {event.start_date:%b %d, %Y} has reached maximum capacity ({event.capacity} people). Registration is now closed.',
                link=f"/events/{event.pk}/",
            )

    # Always open the pre-filled Google Form so the response lands in Sheets
    # The form is pre-filled with the event ID so Sheets tracks which event
    form_url = event.get_registration_url()
    messages.success(request, f'Registration confirmed! Please complete the form to finalise your spot.')
    # Redirect to a page that shows both the success message AND opens the form
    return render(request, "events/register_redirect.html", {
        "event": event,
        "form_url": form_url,
    })


@login_required
def cancel_registration(request, pk):
    EventRegistration.objects.filter(event_id=pk, participant=request.user).delete()
    notify_managers(
        "Event registration cancelled",
        f"{request.user} cancelled their registration for event #{pk}.",
    )
    messages.success(request, "Registration cancelled.")
    return redirect("events:detail", pk=pk)


def qr_scan(request, qr_uuid):
    """
    Stable portal QR-code scan handler — keyed by qr_uuid so printed codes
    never break even if the event is edited.

    Flow for BOTH phone camera and portal users:
      → Record in portal DB (if authenticated)
      → Open pre-filled Google Form (event ID pre-filled) so every
         registration is captured in Google Sheets regardless of source.

    The pre-filled Event ID field in the form lets you filter Google Sheets
    responses by event — both QR scans and direct portal registrations appear
    in the same sheet, tagged with the event's portal ID.
    """
    event = get_object_or_404(Event, qr_uuid=qr_uuid)

    # Build the pre-filled form URL for this specific event
    form_url = event.get_registration_url()

    # ── Unauthenticated (phone camera scan) ──────────────────────────────
    if not request.user.is_authenticated:
        # Go straight to the pre-filled Google Form
        return redirect(form_url)

    # ── Authenticated portal user ────────────────────────────────────────
    if event.is_past:
        messages.warning(request, f'"{event.title}" has already ended. Registration is closed.')
        return redirect("events:detail", pk=event.pk)

    if event.is_full:
        messages.warning(request, f'"{event.title}" is fully booked ({event.capacity}/{event.capacity}).')
        return redirect("events:detail", pk=event.pk)

    # Record in portal DB
    EventRegistration.objects.get_or_create(event=event, participant=request.user)
    _, created = EventAttendance.objects.get_or_create(event=event, participant=request.user)
    if created:
        notify_user(
            request.user,
            f"Attendance recorded: {event.title}",
            f'Your attendance at "{event.title}" has been recorded via QR code. Thank you for joining!',
            link=f"/events/{event.pk}/",
        )
        notify_managers(
            f"Event attendance (QR): {event.title}",
            f'{request.user} scanned in to "{event.title}".',
            link=f"/events/{event.pk}/",
        )

    if event.is_full:
        notify_all(
            f"Event fully booked: {event.title}",
            f'"{event.title}" has reached maximum capacity ({event.capacity} people). Registration is now closed.',
            link=f"/events/{event.pk}/",
        )

    # Show an intermediate page that confirms the DB record and opens the form
    return render(request, "events/register_redirect.html", {
        "event": event,
        "form_url": form_url,
        "via_qr": True,
    })


def qr_attend(request, pk):
    """
    Legacy QR code scan handler (kept for backward compatibility).
    New QR codes use qr_scan() via /events/qr/<uuid>/.
    """
    event = get_object_or_404(Event, pk=pk)
    google_form_url = event.get_registration_url()

    if request.user.is_authenticated:
        EventRegistration.objects.get_or_create(event=event, participant=request.user)
        _, created = EventAttendance.objects.get_or_create(event=event, participant=request.user)
        if created:
            notify_user(
                request.user,
                f"Attendance recorded: {event.title}",
                f'Your attendance at "{event.title}" has been recorded. Thank you for joining!',
                link=f"/events/{event.pk}/",
            )
            notify_managers(
                f"Event attendance: {event.title}",
                f'{request.user} attended "{event.title}".',
                link=f"/events/{event.pk}/",
            )
        messages.success(
            request,
            f'Attendance recorded for "{event.title}". '
            "Please complete the Google Form to confirm your details.",
        )

    return redirect(google_form_url)


@login_required
def registration_count_api(request, pk):
    """
    AJAX endpoint — returns live registration count and capacity status.
    Called by the event detail page every 30 seconds.
    """
    event = get_object_or_404(Event, pk=pk)
    count = event.registrations.count()
    return JsonResponse({
        "count": count,
        "capacity": event.capacity,
        "is_full": count >= event.capacity,
        "is_past": event.is_past,
        "registration_open": event.registration_open,
    })


@capability_required("can_manage_events")
def regenerate_qr(request, pk):
    """Force-regenerate the QR code for an event."""
    event = get_object_or_404(Event, pk=pk)
    if request.method == "POST":
        event.qr_code = None  # Force regeneration
        event.regenerate_qr(request)
        if event.qr_code:
            Event.objects.filter(pk=pk).update(qr_code=event.qr_code.name)
        messages.success(request, f'QR code for "{event.title}" regenerated.')
    return redirect("events:detail", pk=pk)


@capability_required("can_manage_events")
def report(request, pk, fmt):
    event = get_object_or_404(Event, pk=pk)
    rows = [
        [
            r.participant.get_full_name() or r.participant.username,
            r.participant.email,
            r.registration_date.strftime("%d %b %Y, %H:%M"),
            "Yes" if EventAttendance.objects.filter(event=event, participant=r.participant).exists() else "No",
        ]
        for r in event.registrations.select_related("participant")
    ]
    headers = ["Participant", "Email", "Registration Date", "Attended"]
    if fmt == "xlsx":
        return excel_response(f"event-{event.pk}-{event.title[:30]}-report", headers, rows)
    return pdf_response(
        f"event-{event.pk}-{event.title[:30]}-report",
        f"Event Report: {event.title}",
        headers,
        rows,
    )

import json
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


@csrf_exempt
@require_POST
def form_response_webhook(request, pk):
    """
    Webhook called by Google Apps Script whenever a Google Form response is submitted.
    """
    from django.conf import settings

    secret = getattr(settings, "EVENTS_WEBHOOK_SECRET", "")
    if secret and request.headers.get("X-Webhook-Secret") != secret:
        return JsonResponse({"error": "Forbidden"}, status=403)

    event = get_object_or_404(Event, pk=pk)

    try:
        body = json.loads(request.body) if request.body else {}
    except (ValueError, TypeError):
        body = {}

    Event.objects.filter(pk=pk).update(form_response_count=db_models.F("form_response_count") + 1)
    event.refresh_from_db(fields=["form_response_count"])

    return JsonResponse({
        "ok": True,
        "event_id": event.pk,
        "form_response_count": event.form_response_count,
    })
