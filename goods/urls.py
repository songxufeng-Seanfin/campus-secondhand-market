from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("product/new/", views.product_create, name="product_create"),
    path("product/<int:pk>/", views.product_detail, name="product_detail"),
    path("product/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("product/<int:pk>/delete/", views.product_delete, name="product_delete"),
    path("product/<int:pk>/favorite/", views.favorite_toggle, name="favorite_toggle"),
    path("product/<int:pk>/message/", views.message_create, name="message_create"),
    path("product/<int:pk>/order/", views.order_create, name="order_create"),
    path("product/<int:pk>/checkout/", views.checkout, name="checkout"),
    # 私聊
    path("product/<int:pk>/chat/", views.chat_start, name="chat_start"),
    path("chat/<int:pk>/", views.chat_detail, name="chat_detail"),
    path("chat/<int:pk>/send/", views.chat_send, name="chat_send"),
    path("chat/<int:pk>/poll/", views.chat_poll, name="chat_poll"),
    path("messages/", views.chat_list, name="chat_list"),
    path("my/products/", views.my_products, name="my_products"),
    path("my/favorites/", views.favorites, name="favorites"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/<int:pk>/<str:action>/", views.order_action, name="order_action"),
]
