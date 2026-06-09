import uuid
from io import BytesIO
try:
    import qrcode
except ImportError:
    qrcode = None
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models
from django.urls import reverse
from django.utils import timezone


# ── Google Form URL for event registration ────────────────────────────────────
GOOGLE_FORM_BASE_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSedV4ca8NSItkayTczjXGSQDETcUDpt4u936FxE9ul1rsVl4g"
    "/viewform"
)

# ── Pre-fill field IDs ────────────────────────────────────────────────────────
# To get these values:
#   1. Open your Google Form → ⋮ menu → "Get pre-filled link"
#   2. Fill in something for each field you want to pre-fill → "Get link"
#   3. Inspect the URL — each field appears as  ?entry.XXXXXXXXX=value
#   4. Copy the entry.XXXXXXXXX key for each field below.
#
# Example:  GOOGLE_FORM_EVENT_ID_FIELD = "entry.123456789"
#
# GOOGLE_FORM_EVENT_ID_FIELD   — the "Event ID" field in your form (required for tracking)
# GOOGLE_FORM_EVENT_NAME_FIELD — the "Event Name" field (optional, for display)
#
GOOGLE_FORM_EVENT_ID_FIELD   = ""   # e.g. "entry.123456789"  ← set this
GOOGLE_FORM_EVENT_NAME_FIELD = ""   # e.g. "entry.987654321"  ← optional


def build_form_url(event):
    """
    Return the Google Form URL pre-filled with this event's ID (and optionally
    its name).  Both QR-code scans and the direct portal "Register" button use
    this same URL so every response is automatically tagged with the event.

    If no pre-fill fields are configured the plain base URL is returned.
    """
    import urllib.parse
    params = {}
    if GOOGLE_FORM_EVENT_ID_FIELD:
        params[GOOGLE_FORM_EVENT_ID_FIELD] = str(event.pk)
    if GOOGLE_FORM_EVENT_NAME_FIELD:
        params[GOOGLE_FORM_EVENT_NAME_FIELD] = event.title
    if params:
        return GOOGLE_FORM_BASE_URL + "?" + urllib.parse.urlencode(params)
    return GOOGLE_FORM_BASE_URL


class Event(models.Model):
    title = models.CharField(max_length=220)
    description = models.TextField()
    location = models.CharField(max_length=220)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    capacity = models.PositiveIntegerField(default=50)
    banner = models.FileField(upload_to="event_banners/", blank=True, null=True)
    qr_code = models.FileField(upload_to="event_qr/", blank=True, null=True)

    # Unique ID embedded in the portal QR code — survives regeneration
    qr_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # Store the Google Form URL so admins can see / override it
    google_form_url = models.URLField(
        blank=True,
        help_text=(
            "Auto-generated Google Form URL. "
            "Override with a custom form URL if needed. "
            "The QR code will point to this URL."
        ),
    )

    # Auto-updated from Google Forms webhook — reflects actual form submissions
    form_response_count = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Number of Google Form responses received for this event. "
            "Auto-updated via the /events/<pk>/form-response/ webhook "
            "triggered by Google Apps Script."
        ),
    )

    class Meta:
        ordering = ("start_date",)

    def __str__(self):
        return self.title

    @property
    def is_past(self):
        """True once the event's end_date has elapsed."""
        return timezone.now() > self.end_date

    @property
    def is_upcoming(self):
        """True if the event hasn't ended yet."""
        return timezone.now() <= self.end_date

    @property
    def is_full(self):
        """True when registrations have reached or exceeded capacity."""
        return self.registrations.count() >= self.capacity

    @property
    def registration_open(self):
        """Registration is open only when the event is upcoming AND not full."""
        return self.is_upcoming and not self.is_full

    def registration_count(self):
        return self.registrations.count()

    def attendance_count(self):
        return self.attendance.count()

    def get_portal_qr_url(self, request=None):
        """
        Return the portal registration URL embedded in the QR code.
        Uses the event's stable qr_uuid so the URL never changes even if the
        event PK changes.  The view at /events/qr/<uuid>/ handles both
        authenticated and unauthenticated users.
        """
        path = f"/events/qr/{self.qr_uuid}/"
        if request:
            return request.build_absolute_uri(path)
        base = getattr(settings, "SITE_BASE_URL", "").rstrip("/")
        return f"{base}{path}" if base else path

    def get_registration_url(self):
        """
        Return the Google Form URL pre-filled with this event's ID.
        Used by both the direct "Register" button and the QR code redirect,
        so every form submission is automatically tagged with the event.
        """
        return build_form_url(self)

    def regenerate_qr(self, request=None):
        """
        Regenerate the QR code.

        The QR encodes the portal's own /events/qr/<uuid>/ endpoint.
        - Phone camera (unauthenticated): portal redirects to the pre-filled
          Google Form URL for this specific event.
        - Portal user (authenticated): attendance is recorded in the DB, then
          the same pre-filled Google Form opens so the response is also
          captured in Google Sheets.

        The UUID is stable — regenerating never breaks existing printed codes.
        """
        if not qrcode:
            return
        url = self.get_portal_qr_url(request)
        img = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=12,
            border=4,
        )
        img.add_data(url)
        img.make(fit=True)
        qr_img = img.make_image(fill_color="#1e40af", back_color="white")
        buffer = BytesIO()
        qr_img.save(buffer, format="PNG")
        self.qr_code.save(
            f"event-{self.pk}-{str(self.qr_uuid)[:8]}.png",
            ContentFile(buffer.getvalue()),
            save=False,
        )

    def save(self, *args, **kwargs):
        # Store the base form URL (without pre-fill params — those are added at runtime)
        self.google_form_url = GOOGLE_FORM_BASE_URL

        super().save(*args, **kwargs)

        # Auto-generate QR code on first save only (regenerate_qr() for manual refresh)
        if qrcode and not self.qr_code:
            self.regenerate_qr()
            Event.objects.filter(pk=self.pk).update(
                qr_code=self.qr_code.name if self.qr_code else "",
                google_form_url=self.google_form_url,
            )


class EventRegistration(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    participant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_registrations")
    registration_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "participant")


class EventAttendance(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="attendance")
    participant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_attendance")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "participant")
