from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('dashboard:login')
        if not request.user.is_staff and not request.user.is_superuser:
            messages.error(request, 'Access denied. Staff only.')
            return redirect('dashboard:login')
        return view_func(request, *args, **kwargs)
    return wrapper
