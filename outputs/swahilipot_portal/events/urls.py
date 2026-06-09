from django.urls import path
from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="list"),
    path("new/", views.event_create, name="create"),
    path("<int:pk>/", views.event_detail, name="detail"),
    path("<int:pk>/register/", views.register, name="register"),
    path("<int:pk>/cancel/", views.cancel_registration, name="cancel"),
    path("<int:pk>/attend/", views.qr_attend, name="qr_attend"),
    path("<int:pk>/regenerate-qr/", views.regenerate_qr, name="regenerate_qr"),
    path("<int:pk>/report/<str:fmt>/", views.report, name="report"),
    # Stable portal QR-code scan URL — keyed by UUID so printed codes never break
    path("qr/<uuid:qr_uuid>/", views.qr_scan, name="qr_scan"),
    # Live registration count (AJAX) for the event detail page
    path("<int:pk>/registration-count/", views.registration_count_api, name="registration_count"),
    # Google Form webhook — called by Apps Script on every form submission
    path("<int:pk>/form-response/", views.form_response_webhook, name="form_response_webhook"),
]
