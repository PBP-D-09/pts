from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import CustomUser


def account_type_required(account_type):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if request.user.account_type != account_type:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapped_view

    return decorator


customer_required = account_type_required(CustomUser.AccountType.CUSTOMER)
tenant_required = account_type_required(CustomUser.AccountType.TENANT)
