from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views
from .forms import LoginForm

urlpatterns = [
    path("register/", views.register, name="register"),
    path(
        "login/",
        LoginView.as_view(template_name="login.html", authentication_form=LoginForm),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
]
