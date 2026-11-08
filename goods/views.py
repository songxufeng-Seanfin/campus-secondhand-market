from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import F, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ProductForm
from .models import Category, Favorite, Order, Product, ProductMessage


def _base_queryset():
    """商品列表的公共查询集：只查上架且未售出的，并预取关联对象。

    select_related 把 seller / category 一次 JOIN 出来；
    Prefetch 把「进行中订单」一次性取出来，模板里判断“已预订”时不再逐条查库，
    避免列表页出现 N+1 查询（这是 Django 性能优化第一课）。
    """
    active_orders = Order.objects.filter(status__in=Order.ACTIVE_STATUSES).select_related("buyer")
    return (
        Product.objects.filter(is_active=True, is_sold=False)
        .select_related("seller", "category")
        .prefetch_related(Prefetch("orders", queryset=active_orders, to_attr="active_orders"))
    )


def home(request):
    """首页：商品列表 + 关键词搜索 + 分类筛选 + 分页。"""
    products = _base_queryset()

    keyword = request.GET.get("q", "").strip()
    if keyword:
        # Q 对象做“或”查询：标题或描述命中都算
        products = products.filter(
            Q(title__icontains=keyword) | Q(description__icontains=keyword)
        )

    current_slug = request.GET.get("category", "").strip()
    if current_slug:
        products = products.filter(category__slug=current_slug)

    paginator = Paginator(products, 9)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "categories": Category.objects.all(),
        "keyword": keyword,
        "current_category": current_slug,
        "total_count": products.count(),
    }
    return render(request, "home.html", context)


def product_detail(request, pk):
    """商品详情：浏览量 +1 用 F 表达式在数据库层自增，避免并发丢更新。"""
    product = get_object_or_404(
        Product.objects.select_related("seller", "category"), pk=pk
    )
    Product.objects.filter(pk=pk).update(views=F("views") + 1)
    product.refresh_from_db(fields=["views"])

    related = (
        _base_queryset()
        .filter(category=product.category)
        .exclude(pk=product.pk)[:3]
    )

    # 当前用户与这件商品的关系：是否收藏、是否已下单
    is_favorited = False
    my_order = None
    if request.user.is_authenticated:
        is_favorited = Favorite.objects.filter(user=request.user, product=product).exists()
        my_order = (
            Order.objects.filter(product=product, buyer=request.user)
            .order_by("-created_at")
            .first()
        )

    context = {
        "product": product,
        "related": related,
        "is_favorited": is_favorited,
        "my_order": my_order,
        "product_messages": product.messages.select_related("author"),
        "favorite_count": product.favorited_by.count(),
    }
    return render(request, "product_detail.html", context)


@login_required
def product_create(request):
    """发布闲置：登录后才能访问（未登录会被 LOGIN_URL 拦到登录页）。"""
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.seller = request.user  # 卖家永远是当前登录用户，不信任前端传值
            product.save()
            messages.success(request, "发布成功！你的闲置已经出现在集市上了 🎉")
            return redirect("product_detail", pk=product.pk)
    else:
        form = ProductForm()
    return render(request, "product_form.html", {"form": form, "is_edit": False})


@login_required
def product_edit(request, pk):
    """编辑商品：只有卖家本人可以改，其他人 403。"""
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "已保存修改")
            return redirect("product_detail", pk=product.pk)
    else:
        form = ProductForm(instance=product)
    return render(request, "product_form.html", {"form": form, "is_edit": True, "product": product})


@login_required
def product_delete(request, pk):
    """下架商品：POST 才执行删除，GET 只做二次确认（防止链接触发误删）。"""
    product = get_object_or_404(Product, pk=pk, seller=request.user)
    if request.method == "POST":
        product.delete()
        messages.success(request, "商品已删除")
        return redirect("my_products")
    return render(request, "product_confirm_delete.html", {"product": product})


@login_required
def my_products(request):
    """我的闲置：包含在售、已售出和已下架的全部商品。"""
    products = (
        Product.objects.filter(seller=request.user)
        .select_related("category")
        .prefetch_related(
            Prefetch(
                "orders",
                queryset=Order.objects.filter(status__in=Order.ACTIVE_STATUSES).select_related("buyer"),
                to_attr="active_orders",
            )
        )
        .order_by("-created_at")
    )
    return render(request, "my_products.html", {"products": products})


# ============================ 订单 ============================


@login_required
@require_POST
def order_create(request, pk):
    """买家下单（提交购买意向）。

    - 不能买自己的东西；
    - 商品必须仍然可售（上架、未售出、没有进行中的订单）；
    - 数据库唯一约束兜底：连点两次也只会产生一张进行中的订单。
    """
    product = get_object_or_404(Product.objects.select_related("seller"), pk=pk)

    if product.seller_id == request.user.id:
        messages.error(request, "不能购买自己发布的闲置")
        return redirect("product_detail", pk=pk)

    if not product.is_on_sale:
        messages.error(request, "这件闲置已经被预订或售出了，看看同类好物吧")
        return redirect("product_detail", pk=pk)

    note = (request.POST.get("message") or "").strip()[:120]
    try:
        with transaction.atomic():
            Order.objects.create(
                product=product,
                buyer=request.user,
                seller=product.seller,
                price=product.price,
                message=note,
            )
    except IntegrityError:
        messages.info(request, "你已经下过单了，去「我的订单」看看进度吧")
    else:
        messages.success(request, "已提交购买意向，等卖家确认后就能约时间交易啦")
    return redirect("order_list")


@login_required
def order_list(request):
    """订单中心：我买到的 / 我卖出的，两个标签页。"""
    tab = request.GET.get("tab") or "bought"
    qs = Order.objects.select_related("product", "product__category", "buyer", "seller")

    if tab == "sold":
        orders = qs.filter(seller=request.user)
    else:
        tab = "bought"
        orders = qs.filter(buyer=request.user)

    context = {
        "orders": orders,
        "tab": tab,
        "bought_count": Order.objects.filter(buyer=request.user).count(),
        "sold_count": Order.objects.filter(seller=request.user).count(),
        "pending_count": Order.objects.filter(seller=request.user, status="pending").count(),
    }
    return render(request, "orders.html", context)


@login_required
@require_POST
def order_action(request, pk, action):
    """订单状态流转。

    权限和状态都在服务端校验：前端藏按钮只是体验，不能当作安全边界。
    """
    order = get_object_or_404(Order.objects.select_related("product"), pk=pk)
    is_buyer = order.buyer_id == request.user.id
    is_seller = order.seller_id == request.user.id

    with transaction.atomic():
        if action == "accept" and is_seller and order.status == "pending":
            order.status = "accepted"
            order.save(update_fields=["status", "updated_at"])
            messages.success(request, "已确认订单，记得和买家约好交易时间地点")

        elif action == "reject" and is_seller and order.status == "pending":
            order.status = "rejected"
            order.save(update_fields=["status", "updated_at"])
            messages.info(request, "已拒绝这笔订单，商品重新回到集市")

        elif action == "cancel" and is_buyer and order.is_active:
            order.status = "cancelled"
            order.save(update_fields=["status", "updated_at"])
            messages.info(request, "订单已取消")

        elif action == "complete" and order.status == "accepted" and (is_buyer or is_seller):
            order.status = "completed"
            order.save(update_fields=["status", "updated_at"])
            # 交易完成：商品标记售出，同一商品的其他进行中订单自动关闭
            product = order.product
            product.is_sold = True
            product.save(update_fields=["is_sold", "updated_at"])
            Order.objects.filter(
                product=product, status__in=Order.ACTIVE_STATUSES
            ).exclude(pk=order.pk).update(status="cancelled")
            messages.success(request, "交易完成，这件闲置找到新主人啦 🎉")

        else:
            messages.error(request, "当前状态下不能执行这个操作")

    return redirect("order_list")


# ============================ 收藏 ============================


def _safe_next(request, fallback):
    """只允许站内相对路径跳转，避免 next 参数被拿来做开放重定向。"""
    nxt = (request.POST.get("next") or "").strip()
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return fallback


@login_required
@require_POST
def favorite_toggle(request, pk):
    """收藏 / 取消收藏：同一个接口切换，返回来源页面。"""
    product = get_object_or_404(Product, pk=pk)
    favorite, created = Favorite.objects.get_or_create(user=request.user, product=product)
    if created:
        messages.success(request, "已加入收藏，去「我的收藏」随时找回来")
    else:
        favorite.delete()
        messages.info(request, "已取消收藏")
    return redirect(_safe_next(request, product.get_absolute_url()))


@login_required
def favorites(request):
    """我的收藏：顺手把已售出的也标出来，方便用户知道哪些已经没了。"""
    items = (
        Favorite.objects.filter(user=request.user)
        .select_related("product", "product__category", "product__seller")
        .order_by("-created_at")
    )
    return render(request, "favorites.html", {"favorites": items})


# ============================ 商品留言 ============================


@login_required
@require_POST
def message_create(request, pk):
    """在商品详情页留言。卖家回复也走这里，模板里用“卖家”标签区分。"""
    product = get_object_or_404(Product, pk=pk)
    body = (request.POST.get("body") or "").strip()

    if not body:
        messages.error(request, "留言不能为空")
    elif len(body) > 200:
        messages.error(request, "留言太长了，控制在 200 字以内")
    else:
        ProductMessage.objects.create(product=product, author=request.user, body=body)

    return redirect(f"{product.get_absolute_url()}#messages")
