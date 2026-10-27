from .services import count_cart_items


def cart(request):
    """Jumlah item keranjang untuk badge Cart di header."""
    return {"cart_item_count": count_cart_items(request)}
