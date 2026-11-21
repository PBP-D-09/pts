from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from apps.accounts.permissions import IsCustomer
from apps.map.models import DeliveryAddress

from . import selectors, services
from .models import Order
from .serializers import (
    CartItemAddSerializer,
    CartItemSerializer,
    CartItemUpdateSerializer,
    CheckoutAddressSerializer,
    CheckoutSerializer,
    OrderNoteSerializer,
    OrderSerializer,
)

NOT_FOUND_CART_ITEM = {"detail": "Item keranjang tidak ditemukan."}
EMPTY_CART = {"detail": "Your cart is empty."}
NOTE_LOCKED = "The tenant is already preparing this order, so the note is locked."


def _cart_payload(cart, request) -> dict:
    items = services.get_cart_items(cart)
    return {
        "id": str(cart.id),
        "total_items": sum(item.quantity for item in items),
        "tenant_count": len(services.get_cart_tenants(items)),
        "subtotal": sum(item.subtotal for item in items),
        "items": CartItemSerializer(
            items, many=True, context={"request": request}
        ).data,
    }


def _own_order(request, order_id):
    return get_object_or_404(
        Order.objects.prefetch_related("items"), id=order_id, user=request.user
    )


# --- Keranjang ----------------------------------------------------------


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomer])
def cart_api(request):
    cart = services.get_user_cart(request.user)
    return Response(_cart_payload(cart, request))


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomer])
def cart_items_api(request):
    serializer = CartItemAddSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    cart = services.get_user_cart(request.user)
    services.add_item_to_cart(
        cart,
        serializer.validated_data["menu_item_id"],
        serializer.validated_data["quantity"],
    )
    return Response(_cart_payload(cart, request), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomer])
def cart_item_detail_api(request, item_id):
    cart = services.get_user_cart(request.user)
    if request.method == "DELETE":
        if not services.remove_cart_item(cart, item_id):
            return Response(NOT_FOUND_CART_ITEM, status=status.HTTP_404_NOT_FOUND)
        return Response(_cart_payload(cart, request))

    serializer = CartItemUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    updated = services.update_cart_item_quantity(
        cart, item_id, serializer.validated_data["quantity"]
    )
    if updated is None:
        return Response(NOT_FOUND_CART_ITEM, status=status.HTTP_404_NOT_FOUND)
    return Response(_cart_payload(cart, request))


# --- Checkout -----------------------------------------------------------


@api_view(["GET", "POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomer])
def checkout_api(request):
    cart = services.get_user_cart(request.user)
    items = services.get_cart_items(cart)
    if not items:
        return Response(EMPTY_CART, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "POST":
        serializer = CheckoutSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            order = services.create_order_from_cart(
                user=request.user,
                cart=cart,
                packaging_type=serializer.validated_data["packaging_type"],
                address=serializer.validated_data["address_id"],
                delivery_notes=serializer.validated_data["delivery_notes"],
            )
        except ValueError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    # GET: ringkasan checkout (alamat + ongkir, pilihan kemasan) untuk form.
    tenants = services.get_cart_tenants(items)
    addresses = list(DeliveryAddress.objects.filter(owner=request.user))
    for address in addresses:
        address.quote = services.quote_delivery(address, tenants)
    default_address = next(
        (address for address in addresses if address.is_default),
        addresses[0] if addresses else None,
    )
    return Response(
        {
            "cart": _cart_payload(cart, request),
            "addresses": CheckoutAddressSerializer(addresses, many=True).data,
            "default_address_id": default_address.pk if default_address else None,
            "packaging_options": services.get_packaging_options(
                services.get_reusable_stocks(tenants)
            ),
        }
    )


# --- Riwayat pesanan ----------------------------------------------------


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomer])
def orders_api(request):
    orders, active_status, date_range = selectors.filter_user_orders(
        request.user, request.query_params
    )
    results = OrderSerializer(orders, many=True).data
    return Response(
        {
            "status_counts": selectors.status_counts(request.user),
            "active_status": active_status,
            "date_range": date_range,
            "unreturned_containers": services.get_user_unreturned_containers_count(
                request.user
            ),
            "container_return_points": services.CONTAINER_RETURN_POINTS,
            "count": len(results),
            "results": results,
        }
    )


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomer])
def order_detail_api(request, order_id):
    return Response(OrderSerializer(_own_order(request, order_id)).data)


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomer])
def order_cancel_api(request, order_id):
    order = _own_order(request, order_id)
    try:
        order = services.cancel_order(order)
    except ValueError as err:
        return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(OrderSerializer(order).data)


@api_view(["PATCH"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomer])
def order_note_api(request, order_id):
    order = _own_order(request, order_id)
    if not order.can_edit_note:
        return Response({"detail": NOTE_LOCKED}, status=status.HTTP_400_BAD_REQUEST)
    serializer = OrderNoteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    order.delivery_notes = serializer.validated_data["delivery_notes"].strip()
    order.save(update_fields=["delivery_notes", "updated_at"])
    return Response(OrderSerializer(order).data)


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsCustomer])
def order_reorder_api(request, order_id):
    order = _own_order(request, order_id)
    cart = services.get_user_cart(request.user)
    added_count = services.reorder_items_to_cart(order, cart)
    return Response({"added_count": added_count, "cart": _cart_payload(cart, request)})
