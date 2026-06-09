from django.contrib import admin
from django.contrib import messages
from .models import Event, EventAttendance, EventRegistration


def regenerate_qr_codes(modeladmin, request, queryset):
    """Admin action: regenerate QR codes for selected events."""
    count = 0
    for event in queryset:
        # Clear the stored form URL so it gets rebuilt from the new base URL
        event.google_form_url = ""
        event.save()
        count += 1
    modeladmin.message_user(
        request,
        f"QR codes regenerated for {count} event(s). They now point to the real Google Form.",
        messages.SUCCESS,
    )

regenerate_qr_codes.short_description = "Regenerate QR codes (point to Google Form)"


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display  = ("title", "location", "start_date", "registration_count", "attendance_count")
    actions       = [regenerate_qr_codes]
    readonly_fields = ("qr_code",)


admin.site.register(EventRegistration)
admin.site.register(EventAttendance)
