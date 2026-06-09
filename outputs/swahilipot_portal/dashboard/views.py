from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone
from accounts.models import User
from attendance.models import Attendance
from communication.models import Announcement
from core.permissions import capability_required
from core.reports import excel_response, pdf_response
from events.models import Event
from suggestions.models import Suggestion
from tasks.models import Task
from tasks.access import visible_tasks_for


@login_required
def home(request):
    today = timezone.localdate()
    user_records = Attendance.objects.filter(user=request.user)[:5]

    # Tasks scoped to this user's role
    visible_tasks = visible_tasks_for(request.user)

    # Calendar reminders: upcoming tasks + events for this user
    from tasks.models import Task as _Task
    from events.models import Event as _Event
    import json as _json
    from django.utils.timezone import make_aware
    from datetime import datetime as _dt

    upcoming_tasks = visible_tasks.exclude(
        status__in=["completed"]
    ).order_by("due_date")[:30]

    upcoming_events = _Event.objects.filter(
        start_date__date__gte=today
    ).order_by("start_date")[:20]

    # Build calendar items list for JS (ISO date + title + type + priority)
    cal_items = []
    for t in upcoming_tasks:
        cal_items.append({
            "title": t.title,
            "date": t.due_date.isoformat(),
            "type": "task",
            "priority": t.priority,
            "url": f"/tasks/{t.pk}/",
        })
    for e in upcoming_events:
        cal_items.append({
            "title": e.title,
            "date": e.start_date.date().isoformat(),
            "type": "event",
            "priority": "medium",
            "url": f"/events/{e.pk}/",
        })

    context = {
        "announcements": Announcement.objects.all()[:5],
        "my_tasks": visible_tasks[:5],
        "my_attendance": user_records,
        # Only show events that haven't ended yet on the dashboard
        "events": _Event.objects.filter(end_date__gte=timezone.now()).order_by("start_date")[:5],
        "total_staff": User.objects.filter(is_active=True).count(),
        "attendance_today": Attendance.objects.filter(check_in_time__date=today).count(),
        "checked_in_now": Attendance.objects.filter(status=Attendance.Status.CHECKED_IN).count(),
        "late_arrivals": Attendance.objects.filter(
            check_in_time__date=today,
            arrival_status=Attendance.ArrivalStatus.LATE,
        ).count(),
        # Users who have NOT checked in at all today (active users only)
        "not_checked_in": User.objects.filter(is_active=True).exclude(
            attendance_records__check_in_time__date=today
        ).count(),
        # Task analytics only over tasks the user can see (role-scoped)
        "task_status": list(visible_tasks.values("status").annotate(count=Count("id"))),
        "task_status_total": max(visible_tasks.values("status").annotate(count=Count("id")).aggregate(t=Count("id"))["t"] or 1, 1),
        "suggestion_categories": list(Suggestion.objects.values("category").annotate(count=Count("id"))),
        "suggestion_categories_total": max(Suggestion.objects.count() or 1, 1),
        "event_stats": list(
            _Event.objects.annotate(
                reg_count=Count("registrations"),
                att_count=Count("attendance")
            ).values("title", "reg_count", "att_count")[:8]
        ),
        # Reminders calendar
        "cal_items_json": _json.dumps(cal_items),
        "today_iso": today.isoformat(),
    }
    return render(request, "dashboard/home.html", context)


def filtered_dates(request, qs, field):
    start = request.GET.get("start")
    end = request.GET.get("end")
    if start:
        qs = qs.filter(**{f"{field}__date__gte": start})
    if end:
        qs = qs.filter(**{f"{field}__date__lte": end})
    return qs


@capability_required("can_view_reports")
def reports(request):
    return render(request, "dashboard/reports.html")


@login_required
def reminders(request):
    """Full-page calendar + reminders view for all users."""
    import json as _json
    from tasks.models import Task as _Task
    from events.models import Event as _Event

    today = timezone.localdate()
    visible_tasks = visible_tasks_for(request.user)

    upcoming_tasks = visible_tasks.exclude(status="completed").order_by("due_date")[:50]
    upcoming_events = _Event.objects.filter(start_date__date__gte=today).order_by("start_date")[:30]

    cal_items = []
    for t in upcoming_tasks:
        cal_items.append({
            "title": t.title,
            "date": t.due_date.isoformat(),
            "type": "task",
            "priority": t.priority,
            "url": f"/tasks/{t.pk}/",
            "status": t.status,
        })
    for e in upcoming_events:
        cal_items.append({
            "title": e.title,
            "date": e.start_date.date().isoformat(),
            "type": "event",
            "priority": "medium",
            "url": f"/events/{e.pk}/",
            "status": "upcoming",
        })

    return render(request, "dashboard/reminders.html", {
        "cal_items_json": _json.dumps(cal_items),
        "today_iso": today.isoformat(),
        "upcoming_tasks": upcoming_tasks,
        "upcoming_events": upcoming_events,
    })


@capability_required("can_view_reports")
def report_download(request, kind, fmt):
    if kind == "attendance":
        qs = filtered_dates(request, Attendance.objects.select_related("user", "project_site"), "check_in_time")
        headers = ["User", "Site", "Check In", "Check Out", "Hours", "Arrival Status", "Departure Status"]
        rows = [
            [
                r.user.username,
                r.project_site.name,
                r.check_in_time,
                r.check_out_time or "",
                r.total_hours,
                r.get_arrival_status_display(),
                r.get_departure_status_display(),
            ]
            for r in qs
        ]
    elif kind == "tasks":
        # Task reports respect role-based visibility
        qs = filtered_dates(request, visible_tasks_for(request.user), "created_at")
        headers = ["Title", "Assigned To", "Assigned By", "Priority", "Status", "Due Date"]
        rows = [
            [
                t.title,
                t.assigned_to.username,
                t.assigned_by.username if t.assigned_by else "",
                t.get_priority_display(),
                t.get_status_display(),
                t.due_date,
            ]
            for t in qs
        ]
    elif kind == "events":
        qs = filtered_dates(request, Event.objects.all(), "start_date")
        headers = ["Title", "Location", "Start", "Registrations", "Attendance"]
        rows = [[e.title, e.location, e.start_date, e.registration_count(), e.attendance_count()] for e in qs]
    elif kind == "location_timeout":
        from attendance.models import LocationLog
        qs = LocationLog.objects.select_related("user").order_by("-turned_off_at")
        start = request.GET.get("start")
        end = request.GET.get("end")
        if start:
            qs = qs.filter(turned_off_at__date__gte=start)
        if end:
            qs = qs.filter(turned_off_at__date__lte=end)
        from django.utils import timezone as _tz
        headers = ["User", "Location Off At", "Location On At", "Duration Off", "Status"]
        rows = [
            [
                log.user.get_full_name() or log.user.username,
                _tz.localtime(log.turned_off_at).strftime("%d %b %Y %H:%M") if log.turned_off_at else "",
                _tz.localtime(log.turned_on_at).strftime("%d %b %Y %H:%M") if log.turned_on_at else "—",
                log.duration_display,
                "Closed" if log.turned_on_at else "Still Off",
            ]
            for log in qs
        ]
    else:
        qs = filtered_dates(request, Suggestion.objects.all(), "submitted_at")
        headers = ["Title", "Category", "Status", "Anonymous", "Submitted At"]
        rows = [[s.title, s.get_category_display(), s.get_status_display(), s.anonymous, s.submitted_at] for s in qs]

    filename = f"{kind}-report"
    if fmt == "xlsx":
        return excel_response(filename, headers, rows)
    return pdf_response(filename, filename.replace("-", " ").title(), headers, rows)
