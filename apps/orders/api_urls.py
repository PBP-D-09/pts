from django.urls import path

from . import api_views

app_name = "orders_api"

urlpatterns = [
    path("", api_views.orders_api, name="orders"),
    path("cart/", api_views.cart_api, name="cart"),
    path("cart/items/", api_views.cart_items_api, name="cart-items"),
    path(
        "cart/items/<uuid:item_id>/",
        api_views.cart_item_detail_api,
        name="cart-item-detail",
    ),
    path("checkout/", api_views.checkout_api, name="checkout"),
    path("<uuid:order_id>/", api_views.order_detail_api, name="order-detail"),
    path("<uuid:order_id>/cancel/", api_views.order_cancel_api, name="order-cancel"),
    path("<uuid:order_id>/note/", api_views.order_note_api, name="order-note"),
    path(
        "<uuid:order_id>/reorder/",
        api_views.order_reorder_api,
        name="order-reorder",
    ),
]
