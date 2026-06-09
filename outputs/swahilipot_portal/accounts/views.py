from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from core.permissions import role_required
from .forms import ProfileForm, UserEditForm
from .models import User, Department


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})


@role_required("admin")
def user_directory(request):
    """Admin panel — all users grouped by role."""
    roles = [
        ("admin",           "Admin",           "danger"),
        ("program_manager", "Program Manager", "primary"),
        ("department_head", "Department Head", "purple"),
        ("staff",           "Staff",           "success"),
        ("intern",          "Intern",          "warning"),
    ]
    groups = []
    all_users = (
        User.objects
        .select_related("department")
        .order_by("role", "first_name", "username")
    )
    for role_key, role_label, colour in roles:
        members = [u for u in all_users if u.role == role_key]
        groups.append({
            "key":    role_key,
            "label":  role_label,
            "colour": colour,
            "users":  members,
        })

    # Summary counts for the top cards
    total       = all_users.count()
    active      = all_users.filter(is_active=True).count()
    departments = Department.objects.all()

    return render(request, "accounts/user_directory.html", {
        "groups":      groups,
        "total":       total,
        "active":      active,
        "inactive":    total - active,
        "departments": departments,
    })


@role_required("admin")
def user_edit(request, pk):
    """Admin edits another user's role / department / status."""
    target = get_object_or_404(User, pk=pk)
    form = UserEditForm(request.POST or None, instance=target)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{target} updated successfully.")
        return redirect("accounts:user_directory")
    return render(request, "accounts/user_edit.html", {"form": form, "target": target})


@role_required("admin")
def user_toggle_active(request, pk):
    """Quick-toggle a user's active status."""
    if request.method == "POST":
        target = get_object_or_404(User, pk=pk)
        if target == request.user:
            messages.error(request, "You cannot deactivate your own account.")
        else:
            target.is_active = not target.is_active
            target.save()
            state = "activated" if target.is_active else "deactivated"
            messages.success(request, f"{target} has been {state}.")
    return redirect("accounts:user_directory")


@role_required("admin")
def user_reset_password(request, pk):
    """Admin sets a new password for any user — no email required."""
    from django.contrib.auth.forms import SetPasswordForm
    target = get_object_or_404(User, pk=pk)
    form = SetPasswordForm(target, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        from core.notify import notify_user as _notify
        _notify(
            target,
            "Your password has been reset",
            f"An administrator ({request.user.get_full_name() or request.user.username}) "
            f"has reset your portal password. Please sign in with your new password.",
            priority="high",
            link="/accounts/profile/",
        )
        messages.success(request, f"Password for {target} has been reset.")
        return redirect("accounts:user_directory")
    return render(request, "accounts/reset_password.html", {
        "form": form,
        "target": target,
        "title": f"Reset Password — {target}",
    })


# ── Department management ─────────────────────────────────────────────────

from .models import Department
from django import forms as django_forms


class DepartmentForm(django_forms.ModelForm):
    class Meta:
        model  = Department
        fields = ("name", "description")


@role_required("admin")
def department_list(request):
    departments = Department.objects.prefetch_related("users").all()
    all_unassigned = User.objects.filter(is_active=True, department__isnull=True).order_by("first_name", "username")
    return render(request, "accounts/departments.html", {
        "departments":   departments,
        "all_unassigned": all_unassigned,
    })


@role_required("admin")
def department_create(request):
    form = DepartmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Department created.")
        return redirect("accounts:departments")
    return render(request, "form.html", {"form": form, "title": "Create Department"})


@role_required("admin")
def department_edit(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    form = DepartmentForm(request.POST or None, instance=dept)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Department updated.")
        return redirect("accounts:departments")
    return render(request, "form.html", {"form": form, "title": f"Edit: {dept.name}"})


@role_required("admin")
def department_assign(request, dept_pk):
    """Bulk-assign selected users to a department."""
    dept = get_object_or_404(Department, pk=dept_pk)
    if request.method == "POST":
        user_pks = request.POST.getlist("user_pks")
        User.objects.filter(pk__in=user_pks).update(department=dept)
        messages.success(request, f"Users assigned to {dept.name}.")
    return redirect("accounts:departments")


@role_required("admin")
def department_remove_user(request, dept_pk, user_pk):
    """Remove a single user from a department."""
    if request.method == "POST":
        target = get_object_or_404(User, pk=user_pk)
        if target.department_id == dept_pk:
            target.department = None
            target.save()
            messages.success(request, f"{target} removed from department.")
    return redirect("accounts:departments")


# ── Add User ─────────────────────────────────────────────────────────────

from .forms import AddUserForm


@role_required("admin")
def user_add(request):
    """Admin creates a new user directly in the portal (no DB/admin needed)."""
    form = AddUserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.is_active = True
        user.save()
        from core.notify import notify_user
        notify_user(
            user,
            "Welcome to Swahilipot Hub Portal!",
            f"Your portal account has been created by {request.user.get_full_name() or request.user.username}. "
            f"You can now log in with your username: {user.username}. "
            f"Your role is: {user.get_role_display()}.",
            link="/accounts/profile/",
        )
        messages.success(request, f"User '{user.username}' created successfully.")
        return redirect("accounts:user_directory")
    return render(request, "accounts/add_user.html", {"form": form, "title": "Add New User"})


# ── Department Task Assignment ────────────────────────────────────────────

@role_required("admin")
def department_assign_task(request, dept_pk):
    """
    Assign a task to the whole department or specific members from within
    the departments page.
    """
    from tasks.models import Task
    dept = get_object_or_404(Department, pk=dept_pk)

    if request.method != "POST":
        return redirect("accounts:departments")

    if not request.user.can_manage_tasks():
        messages.error(request, "You do not have permission to assign tasks.")
        return redirect("accounts:departments")

    title       = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    priority    = request.POST.get("priority", Task.Priority.MEDIUM)
    due_date    = request.POST.get("due_date", "")
    assign_mode = request.POST.get("assign_mode", "whole")

    if not title or not description or not due_date:
        messages.error(request, "Title, description and due date are required.")
        return redirect("accounts:departments")

    valid_priorities = {choice[0] for choice in Task.Priority.choices}
    if priority not in valid_priorities:
        priority = Task.Priority.MEDIUM

    if assign_mode == "whole":
        recipients = dept.users.filter(is_active=True)
    elif assign_mode == "specific":
        member_pks = request.POST.getlist("member_pks")
        if not member_pks:
            messages.error(request, "Please select at least one member.")
            return redirect("accounts:departments")
        recipients = dept.users.filter(pk__in=member_pks, is_active=True)
    else:
        messages.error(request, "Invalid task assignment mode.")
        return redirect("accounts:departments")

    recipients = list(recipients)
    if not recipients:
        messages.error(request, "No active department member matched your selection.")
        return redirect("accounts:departments")

    from core.notify import notify_user as _notify_user
    count = 0
    # Map task priority to notification priority
    _priority_map = {
        "low": "low", "medium": "medium", "high": "high", "critical": "critical"
    }
    notif_priority = _priority_map.get(priority, "medium")
    for member in recipients:
        Task.objects.create(
            title=title,
            description=description,
            assigned_to=member,
            assigned_by=request.user,
            priority=priority,
            due_date=due_date,
            status=Task.Status.PENDING,
        )
        _notify_user(
            member,
            f"New task assigned: {title}",
            f"{request.user.get_full_name() or request.user.username} assigned you a task "
            f"via the {dept.name} department: \"{title}\" — due {due_date}. "
            f"Priority: {priority.title()}.",
            priority=notif_priority,
            link="/tasks/",
        )
        count += 1

    messages.success(request, f"Task assigned to {count} member{'s' if count != 1 else ''} in {dept.name}.")
    return redirect("accounts:departments")

