from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import RegisterForm


def register(request):
    """用户注册：表单校验通过后自动登录并跳转首页。"""
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # 注册成功直接登录，省去用户再输一次密码
            login(request, user)
            return redirect("home")
    else:
        form = RegisterForm()
    return render(request, "register.html", {"form": form})


@login_required
def profile(request):
    """个人中心：用户信息 + 各模块入口的计数。"""
    from goods.models import Favorite, Order, Product

    context = {
        "product_count": Product.objects.filter(seller=request.user).count(),
        "bought_count": Order.objects.filter(buyer=request.user).count(),
        "sold_count": Order.objects.filter(seller=request.user).count(),
        "pending_count": Order.objects.filter(seller=request.user, status="pending").count(),
        "favorite_count": Favorite.objects.filter(user=request.user).count(),
    }
    return render(request, "profile.html", context)
