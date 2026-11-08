from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("product/new/", views.product_create, name="product_create"),
    path("product/<int:pk>/", views.product_detail, name="product_detail"),
    path("product/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("product/<int:pk>/delete/", views.product_delete, name="product_delete"),
    path("my/products/", views.my_products, name="my_products"),
]
