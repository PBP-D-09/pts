from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    # Halaman Riwayat Pesanan
    path("", views.order_list_view, name="order_list"),
    path("<uuid:order_id>/cancel/", views.cancel_order_view, name="cancel_order"),
    path(
        "<uuid:order_id>/update-note/",
        views.update_order_note_view,
        name="update_order_note",
    ),
    path("<uuid:order_id>/reorder/", views.reorder_view, name="reorder"),
    path("<uuid:order_id>/placed/", views.order_placed_view, name="order_placed"),
    # Halaman Keranjang Belanja
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/<uuid:menu_item_id>/", views.add_to_cart_view, name="add_to_cart"),
    path(
        "cart/update/<uuid:item_id>/",
        views.update_cart_item_view,
        name="update_cart_item",
    ),
    path(
        "cart/remove/<uuid:item_id>/",
        views.remove_cart_item_view,
        name="remove_cart_item",
    ),
    # Halaman Checkout
    path("checkout/", views.checkout_view, name="checkout"),
    # REST JSON API Endpoints (Mobile Flutter)
    path("api/cart/", views.api_cart, name="api_cart"),
    path("api/orders/", views.api_orders_list, name="api_orders_list"),
]
