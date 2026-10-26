from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import ReviewFilterForm, ReviewForm
from .integration import resolve_menu, resolve_packaging
from .models import HelpfulVote, Review
from .selectors import rating_summary, review_queryset


def is_async(request):
    return request.headers.get("X-Reviews-Request") == "true"


def authenticated(request):
    if request.user.is_authenticated:
        return None
    if is_async(request):
        return JsonResponse({"error": "Log in to continue."}, status=401)
    return redirect_to_login(request.get_full_path(), reverse("accounts:login"))


def customer(request):
    response = authenticated(request)
    if response is not None:
        return response
    if not request.user.is_customer:
        return HttpResponseForbidden("Only customers can write reviews.")


@require_GET
def reviews(request, menu_key):
    menu = resolve_menu(menu_key)
    filters = ReviewFilterForm(request.GET or None)
    if filters.is_bound and not filters.is_valid():
        return render(
            request, "reviews/filter_error.html", {"filter_form": filters}, status=400
        )
    values = filters.cleaned_data if filters.is_bound else {}
    qs = review_queryset(menu_key, request.user, values)
    page = Paginator(qs, 4).get_page(request.GET.get("page"))
    params = request.GET.copy()
    if page.has_next():
        params["page"] = page.next_page_number()
    active = []
    for name in ("rating", "sentiment", "packaging"):
        if values.get(name):
            clear = request.GET.copy()
            clear.pop(name, None)
            clear.pop("page", None)
            active.append(
                (
                    dict(filters.fields[name].choices)[values[name]],
                    "?" + clear.urlencode(),
                )
            )
    context = {
        "menu": menu,
        "page": page,
        "summary": rating_summary(menu_key),
        "filter_form": filters,
        "active_filters": active,
        "next_url": "?" + params.urlencode() if page.has_next() else "",
    }
    template = (
        "reviews/partials/results.html" if is_async(request) else "reviews/reviews.html"
    )
    return render(request, template, context)


@require_http_methods(["GET", "POST"])
def create_review(request, menu_key):
    denied = customer(request)
    if denied is not None:
        return denied
    menu = resolve_menu(menu_key)
    form = ReviewForm(
        request.POST if request.method == "POST" else None, request.FILES or None
    )
    if request.method == "POST" and form.is_valid():
        review = form.save(commit=False)
        review.menu_key, review.author = menu.key, request.user
        review.packaging_type = resolve_packaging(menu_key, request.user)
        review.save()
        return mutation_success(request, menu_key, "Your review has been published.")
    return render(
        request,
        "reviews/form.html",
        {"form": form, "menu": menu},
        status=422 if request.method == "POST" else 200,
    )


@require_http_methods(["GET", "POST"])
@transaction.atomic
def edit_review(request, pk):
    denied = customer(request)
    if denied is not None:
        return denied
    review = get_object_or_404(
        Review.objects.select_for_update(), pk=pk, author=request.user
    )
    menu = resolve_menu(review.menu_key)
    form = ReviewForm(
        request.POST if request.method == "POST" else None,
        request.FILES or None,
        instance=review,
    )
    if request.method == "POST" and form.is_valid():
        # ModelForm has already assigned a replacement, so read the old storage name.
        old_photo = Review.objects.get(pk=pk).photo
        with transaction.atomic():
            updated = form.save(commit=False)
            if form.cleaned_data["remove_photo"] and not request.FILES.get("photo"):
                updated.photo = ""
            updated.save()
            if old_photo and old_photo.name != updated.photo.name:
                transaction.on_commit(lambda: old_photo.delete(save=False), robust=True)
        return mutation_success(
            request, review.menu_key, "Your review has been updated."
        )
    return render(
        request,
        "reviews/form.html",
        {"form": form, "menu": menu, "review": review},
        status=422 if request.method == "POST" else 200,
    )


@require_http_methods(["GET", "POST"])
@transaction.atomic
def delete_review(request, pk):
    denied = authenticated(request)
    if denied is not None:
        return denied
    review = get_object_or_404(
        Review.objects.select_for_update(), pk=pk, author=request.user
    )
    try:
        resolve_menu(review.menu_key)
        menu_available = True
    except Http404:
        menu_available = False
    if request.method == "POST":
        menu_key, photo = review.menu_key, review.photo
        with transaction.atomic():
            review.delete()
            if photo:
                transaction.on_commit(lambda: photo.delete(save=False), robust=True)
        return mutation_success(
            request,
            menu_key,
            "Your review has been deleted.",
            url=None if menu_available else reverse("catalog:show_catalog"),
        )
    return render(
        request,
        "reviews/delete.html",
        {"review": review, "menu_available": menu_available},
    )


def mutation_success(request, menu_key, message, url=None):
    url = url or reverse("reviews:menu", args=[menu_key])
    if is_async(request):
        return JsonResponse({"message": message, "url": url})
    messages.success(request, message)
    return redirect(url)


@require_POST
def helpful(request, pk):
    denied = authenticated(request)
    if denied is not None:
        return denied
    with transaction.atomic():
        review = get_object_or_404(Review.objects.select_for_update(), pk=pk)
        resolve_menu(review.menu_key)
        vote, created = HelpfulVote.objects.get_or_create(
            review=review, user=request.user
        )
        if not created:
            vote.delete()
        count = review.helpful_votes.count()
    if is_async(request):
        return JsonResponse({"selected": created, "count": count})
    return redirect("reviews:menu", menu_key=review.menu_key)
