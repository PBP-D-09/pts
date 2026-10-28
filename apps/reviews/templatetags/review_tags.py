from django import template

register = template.Library()


@register.filter
def star_asset(value):
    rating = max(0, min(5, int(float(value or 0) + 0.5)))
    return f"reviews/stars-{rating}.svg"
