from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import Order

DATE_RANGES = {
    "today": "Today",
    "7_days": "Last 7 days",
    "30_days": "Last 30 days",
}


def _parse_date(value):
    """parse_date() yang mengabaikan tanggal tidak valid seperti 2026-02-30."""
    try:
        return parse_date(value)
    except ValueError:
        return None


def status_counts(user) -> dict:
    """Jumlah pesanan per status milik user, ditambah total pada kunci 'all'."""
    rows = (
        Order.objects.filter(user=user)
        .values("status")
        .annotate(total=Count("id"))
        .order_by()
    )
    counts = {status.value: 0 for status in Order.Status}
    for row in rows:
        counts[row["status"]] = row["total"]
    counts["all"] = sum(counts.values())
    return counts


def filter_user_orders(user, params) -> tuple:
    """Riwayat pesanan user yang difilter berdasarkan status dan rentang tanggal.

    `params` berupa QueryDict/dict dengan kunci opsional `status`, `date_range`
    (today | 7_days | 30_days | custom), `start_date`, dan `end_date`. Nilai yang
    tidak dikenal dianggap "all". Mengembalikan (queryset, active_status, date_range).
    """
    orders = Order.objects.filter(user=user).prefetch_related("items__menu_item")

    active_status = params.get("status", "all").strip().lower()
    if active_status in Order.Status.values:
        orders = orders.filter(status=active_status)
    else:
        active_status = "all"

    date_range = params.get("date_range", "all").strip().lower()
    now = timezone.now()
    if date_range == "today":
        orders = orders.filter(created_at__date=timezone.localdate())
    elif date_range == "7_days":
        orders = orders.filter(created_at__gte=now - timedelta(days=7))
    elif date_range == "30_days":
        orders = orders.filter(created_at__gte=now - timedelta(days=30))
    elif date_range == "custom":
        start_date = _parse_date(params.get("start_date", ""))
        end_date = _parse_date(params.get("end_date", ""))
        if start_date:
            orders = orders.filter(created_at__date__gte=start_date)
        if end_date:
            orders = orders.filter(created_at__date__lte=end_date)
    else:
        date_range = "all"

    return orders, active_status, date_range
