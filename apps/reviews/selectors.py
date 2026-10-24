import re

from django.db.models import Avg, Count, Exists, OuterRef

from .models import HelpfulVote, Review

# Transparent local text heuristic (not a rating proxy or external AI service).
POSITIVE = {
    "good",
    "great",
    "fresh",
    "delicious",
    "love",
    "excellent",
    "tasty",
    "perfect",
    "enak",
    "segar",
    "bagus",
    "suka",
    "mantap",
}
NEGATIVE = {
    "bad",
    "poor",
    "bland",
    "leaked",
    "leak",
    "cold",
    "disappointing",
    "terrible",
    "stale",
    "buruk",
    "basi",
    "bocor",
    "hambar",
    "kecewa",
}


def sentiment(text):
    words = re.findall(r"\w+", text.lower())
    score = 0
    for i, word in enumerate(words):
        polarity = int(word in POSITIVE) - int(word in NEGATIVE)
        if i and words[i - 1] in {"not", "no", "tidak", "kurang"}:
            polarity *= -1
        score += polarity
    return "positive" if score > 0 else "negative" if score < 0 else "neutral"


def review_queryset(menu_key, user, filters):
    qs = (
        Review.objects.filter(menu_key=menu_key)
        .select_related("author")
        .annotate(helpful_count=Count("helpful_votes"))
    )
    votes = (
        HelpfulVote.objects.filter(review=OuterRef("pk"), user_id=user.pk)
        if user.is_authenticated
        else HelpfulVote.objects.none()
    )
    qs = qs.annotate(voted=Exists(votes))
    if filters.get("rating"):
        qs = qs.filter(food_rating=int(filters["rating"]))
    if filters.get("packaging"):
        qs = qs.filter(
            packaging_rating__in={
                "very_satisfied": [5],
                "satisfied": [4],
                "neutral": [3],
                "unsatisfied": [1, 2],
            }[filters["packaging"]]
        )
    if filters.get("sentiment"):
        ids = [
            pk
            for pk, text in qs.values_list("pk", "text")
            if sentiment(text) == filters["sentiment"]
        ]
        qs = qs.filter(pk__in=ids)
    ordering = {
        "oldest": ["created_at", "pk"],
        "helpful": ["-helpful_count", "-created_at", "-pk"],
        "highest": ["-food_rating", "-created_at", "-pk"],
    }.get(filters.get("sort"), ["-created_at", "-pk"])
    return qs.order_by(*ordering)


def rating_summary(menu_key):
    qs = Review.objects.filter(menu_key=menu_key)
    data = qs.aggregate(
        total=Count("pk"), food=Avg("food_rating"), packaging=Avg("packaging_rating")
    )
    data["overall"] = ((data["food"] or 0) + (data["packaging"] or 0)) / 2
    counts = dict(
        qs.values("food_rating").annotate(n=Count("pk")).values_list("food_rating", "n")
    )
    data["distribution"] = [
        (i, counts.get(i, 0), counts.get(i, 0) * 100 / (data["total"] or 1))
        for i in range(5, 0, -1)
    ]
    return data
