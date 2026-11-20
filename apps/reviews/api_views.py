import re

from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import selectors, services
from .forms import ReviewFilterForm
from .integration import resolve_menu
from .models import HelpfulVote, Review
from .permissions import IsCustomerForReviewWrites
from .serializers import ReviewSerializer, ReviewWriteSerializer


PAGE_SIZE = 4
MAX_REVIEW_ID = 9223372036854775807


def _parse_review_id(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+", value) is None:
        raise Http404("Review not found.")
    try:
        review_id = int(value)
    except ValueError:
        raise Http404("Review not found.") from None
    if review_id > MAX_REVIEW_ID:
        raise Http404("Review not found.")
    return review_id


def _review_data(review, request):
    return ReviewSerializer(review, context={"request": request}).data


def _summary_data(summary):
    def average(value):
        return round(float(value), 2) if value is not None else None

    return {
        "total": summary["total"],
        "food_average": average(summary["food"]),
        "packaging_average": average(summary["packaging"]),
        "overall_average": average(summary["overall"]),
        "distribution": [
            {
                "rating": rating,
                "count": count,
                "percentage": round(percentage, 2),
            }
            for rating, count, percentage in summary["distribution"]
        ],
    }


def _filter_errors(form):
    return {
        field: [str(error) for error in errors]
        for field, errors in form.errors.items()
    }


@api_view(["GET", "POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomerForReviewWrites])
def menu_reviews_api(request, menu_uuid):
    menu = resolve_menu(str(menu_uuid))
    if request.method == "POST":
        serializer = ReviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = dict(serializer.validated_data)
        validated_data.pop("remove_photo", None)
        review = services.create_review(
            menu_uuid=menu_uuid,
            author=request.user,
            **validated_data,
        )
        review = selectors.review_detail(review.pk, request.user)
        return Response(_review_data(review, request), status=status.HTTP_201_CREATED)

    filter_form = ReviewFilterForm(data=request.query_params)
    if not filter_form.is_valid():
        return Response(
            {"errors": _filter_errors(filter_form)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    queryset = selectors.review_queryset(
        menu.key,
        request.user,
        filter_form.cleaned_data,
    )
    paginator = Paginator(queryset, PAGE_SIZE)
    page = paginator.get_page(request.query_params.get("page"))
    return Response(
        {
            "menu": {
                "uuid": menu.key,
                "name": menu.name,
                "tenant": menu.tenant,
                "description": menu.description,
                "image_url": (
                    request.build_absolute_uri(menu.image_url)
                    if menu.image_url
                    else None
                ),
            },
            "summary": _summary_data(selectors.rating_summary(menu.key)),
            "filters": {
                name: filter_form.cleaned_data.get(name) or None
                for name in ("rating", "sentiment", "packaging", "sort")
            },
            "pagination": {
                "count": paginator.count,
                "page": page.number,
                "page_size": PAGE_SIZE,
                "total_pages": paginator.num_pages,
                "next": page.next_page_number() if page.has_next() else None,
                "previous": page.previous_page_number() if page.has_previous() else None,
            },
            "results": [_review_data(review, request) for review in page.object_list],
        }
    )


@api_view(["GET", "PATCH", "DELETE"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomerForReviewWrites])
def review_detail_api(request, pk):
    pk = _parse_review_id(pk)
    if request.method == "GET":
        review = selectors.review_detail(pk, request.user)
        if review is None:
            raise Http404("Review not found.")
        resolve_menu(review.menu_key)
        return Response(_review_data(review, request))

    with transaction.atomic():
        review = (
            Review.objects.select_for_update()
            .filter(pk=pk, author=request.user)
            .first()
        )
        if review is None:
            raise Http404("Review not found.")
        if request.method == "DELETE":
            services.delete_review(review=review)
            return Response(status=status.HTTP_204_NO_CONTENT)

        resolve_menu(review.menu_key)
        serializer = ReviewWriteSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        services.update_review(review=review, validated_data=serializer.validated_data)
        updated = selectors.review_detail(review.pk, request.user)
        return Response(_review_data(updated, request))


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def helpful_api(request, pk):
    pk = _parse_review_id(pk)
    with transaction.atomic():
        review = Review.objects.select_for_update().filter(pk=pk).first()
        if review is None:
            raise Http404("Review not found.")
        resolve_menu(review.menu_key)
        vote, created = HelpfulVote.objects.get_or_create(
            review=review,
            user=request.user,
        )
        if not created:
            vote.delete()
        count = review.helpful_votes.count()
    return Response(
        {"review_id": review.pk, "selected": created, "helpful_count": count}
    )
