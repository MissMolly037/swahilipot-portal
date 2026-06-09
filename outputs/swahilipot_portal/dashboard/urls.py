from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("reminders/", views.reminders, name="reminders"),
    path("reports/", views.reports, name="reports"),
    path("reports/<str:kind>/<str:fmt>/", views.report_download, name="report_download"),
]
