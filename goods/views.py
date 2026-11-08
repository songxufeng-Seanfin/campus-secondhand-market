from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, OuterRef, Prefetch, Q, Subquery
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ProductForm
from .models import (
    Category,
    ChatMessage,
    Conversation,
    Favorite,
    Order,
    Product,
    ProductMessage,
)


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
    """首页：商品列表 + 关键词搜索 + 分类筛选 + 分页。

    滑动加载时前端带上 X-Requested-With 头，只返回商品卡片片段，
    避免整页 HTML 重复传输；直接访问则照常返回完整页面。
    """
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

    paginator = Paginator(products, 6)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "categories": Category.objects.all(),
        "keyword": keyword,
        "current_category": current_slug,
        "total_count": products.count(),
    }
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        response = render(request, "partials/product_cards.html", context)
        # 前端靠这两个响应头判断还有没有下一页
        response["X-Has-Next"] = "1" if page_obj.has_next() else "0"
        response["X-Next-Page"] = (
            str(page_obj.next_page_number()) if page_obj.has_next() else ""
        )
        return response
    return render(request, "home.html", context)


def product_detail(request, pk):
    """商品详情：浏览量 +1 用 F 表达式在数据库层自增，避免并发丢更新。

    商品不存在（已删除 / 旧链接）时友好跳回首页，避免直接抛 404 错误页。
    """
    try:
        product = Product.objects.select_related("seller", "category").get(pk=pk)
    except Product.DoesNotExist:
        messages.info(request, "这件闲置不存在或已被删除，看看其他好物吧")
        return redirect("home")
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


# ============================ 私聊 ============================


def _conversation_or_404(pk, user):
    """取会话并校验参与身份：不是买卖双方一律 404，不暴露别人聊了什么。"""
    conv = get_object_or_404(
        Conversation.objects.select_related(
            "product", "product__category", "product__seller", "buyer", "seller"
        ),
        pk=pk,
    )
    if not conv.can_access(user):
        raise Http404("会话不存在")
    return conv


def _msg_payload(msg, me_id):
    """消息的最小 JSON 结构，前端轮询和发送共用同一份。"""
    return {
        "id": msg.pk,
        "body": msg.body,
        "sender": msg.sender.username,
        "mine": msg.sender_id == me_id,
        "time": timezone.localtime(msg.created_at).strftime("%m-%d %H:%M"),
    }


@login_required
def chat_start(request, pk):
    """【我想要】/【直接购买】都走这里：拿到（或新建）与卖家的会话。"""
    product = get_object_or_404(Product.objects.select_related("seller"), pk=pk)

    if product.seller_id == request.user.id:
        messages.error(request, "这是你自己发布的闲置，不用私聊自己啦")
        return redirect("product_detail", pk=pk)

    conv, _ = Conversation.objects.get_or_create(
        product=product, buyer=request.user, defaults={"seller": product.seller}
    )
    return redirect("chat_detail", pk=conv.pk)


def _conversation_sidebar(user):
    """左侧会话列表：每个会话带上未读数、最后一条消息和最近活跃时间。

    用 Subquery 取最后一条消息，避免「每个会话再查一次」的 N+1。
    """
    last = ChatMessage.objects.filter(conversation=OuterRef("pk")).order_by("-created_at")
    return (
        Conversation.objects.filter(Q(buyer=user) | Q(seller=user))
        .select_related("product", "product__category", "product__seller", "buyer", "seller")
        .annotate(
            unread=Count(
                "chat_messages",
                filter=Q(chat_messages__is_read=False) & ~Q(chat_messages__sender=user),
            ),
            last_body=Subquery(last.values("body")[:1]),
            last_at=Subquery(last.values("created_at")[:1]),
        )
        .order_by("-updated_at")
    )


@login_required
def chat_detail(request, pk):
    """会话页：左列表 + 右聊天窗（微信式）。打开即把对方消息标为已读。"""
    conv = _conversation_or_404(pk, request.user)

    # 进入会话就算读过了，导航红点随之消失
    conv.chat_messages.exclude(sender=request.user).filter(is_read=False).update(is_read=True)

    chat_messages = list(conv.chat_messages.select_related("sender"))
    last_id = chat_messages[-1].pk if chat_messages else 0

    # 相邻消息超过 10 分钟才显示一次时间分隔，模仿微信的呼吸感
    chat_items = []
    prev_at = None
    for msg in chat_messages:
        local = timezone.localtime(msg.created_at)
        gap = None if prev_at is None else (local - prev_at).total_seconds()
        chat_items.append(
            {
                "msg": msg,
                "show_time": gap is None or gap > 600,
                "time_label": local.strftime("%H:%M")
                if local.date() == timezone.localdate()
                else local.strftime("%m-%d %H:%M"),
            }
        )
        prev_at = local

    # 买家已经下过单就把进度带出来，避免重复下单
    my_order = (
        Order.objects.filter(product=conv.product, buyer=conv.buyer).order_by("-created_at").first()
    )

    return render(
        request,
        "chat_center.html",
        {
            "conversations": _conversation_sidebar(request.user),
            "active": conv,
            "other": conv.other_party(request.user),
            "chat_messages": chat_messages,
            "chat_items": chat_items,
            "last_id": last_id,
            "my_order": my_order,
            "product": conv.product,
        },
    )


@login_required
@require_POST
def chat_send(request, pk):
    """发消息：表单提交走整页刷新，fetch 提交走 JSON 局部更新。"""
    conv = _conversation_or_404(pk, request.user)
    body = (request.POST.get("body") or "").strip()

    if not body:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "说点什么再发送吧"}, status=400)
        messages.error(request, "消息不能为空")
        return redirect("chat_detail", pk=conv.pk)

    msg = ChatMessage.objects.create(
        conversation=conv, sender=request.user, body=body[:300]
    )
    # 触发 updated_at，让这条会话排到消息列表最前面
    conv.save(update_fields=["updated_at"])

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "message": _msg_payload(msg, request.user.id)})
    return redirect("chat_detail", pk=conv.pk)


@login_required
def chat_poll(request, pk):
    """轮询新消息：每 3 秒拉一次，实现对方消息自动出现 + 卖家收到提醒。"""
    conv = _conversation_or_404(pk, request.user)
    try:
        after = int(request.GET.get("after") or 0)
    except ValueError:
        after = 0

    new_msgs = list(conv.chat_messages.filter(pk__gt=after).select_related("sender"))
    if new_msgs:
        # 拉到的消息里凡是对方发的，顺手标记已读（用户此刻就在这个会话里）
        conv.chat_messages.filter(
            pk__gt=after, is_read=False
        ).exclude(sender=request.user).update(is_read=True)

    return JsonResponse(
        {
            "messages": [_msg_payload(m, request.user.id) for m in new_msgs],
            "last_id": new_msgs[-1].pk if new_msgs else after,
        }
    )


@login_required
def chat_list(request):
    """消息中心：左侧会话列表，右侧提示选一个会话（桌面端双栏）。"""
    return render(
        request,
        "chat_center.html",
        {
            "conversations": _conversation_sidebar(request.user),
            "active": None,
        },
    )


# ============================ 订单 ============================


@login_required
def order_create(request, pk):
    """旧入口保留兼容：统一引导到新的下单页（可选择交易方式）。"""
    return redirect("checkout", pk=pk)


@login_required
def checkout(request, pk):
    """下单页：面对面交易 / 线上交易 二选一。

    - 面对面：校内自提，不填地址、不收运费、不走线上支付；
    - 线上：卖家预先设了包邮或不包邮，买家填收货地址后可立即支付。
    付款在这里是演示级「模拟支付」，只改订单支付状态，不接真实支付渠道。
    """
    product = get_object_or_404(Product.objects.select_related("seller", "category"), pk=pk)

    if product.seller_id == request.user.id:
        messages.error(request, "不能购买自己发布的闲置")
        return redirect("product_detail", pk=pk)
    if not product.is_on_sale:
        messages.error(request, "这件闲置已经被预订或售出了，看看同类好物吧")
        return redirect("product_detail", pk=pk)

    conv = Conversation.objects.filter(product=product, buyer=request.user).first()

    if request.method == "POST":
        mode = request.POST.get("trade_mode") or "face"
        if mode not in ("face", "online"):
            messages.error(request, "请选择交易方式")
            return redirect("checkout", pk=pk)

        receiver_name = (request.POST.get("receiver_name") or "").strip()
        receiver_phone = (request.POST.get("receiver_phone") or "").strip()
        address = (request.POST.get("address") or "").strip()
        shipping_fee = product.shipping_fee_amount if mode == "online" else 0

        # 线上交易必须能寄到：收货信息三件套缺一不可
        if mode == "online" and not (receiver_name and receiver_phone and address):
            messages.error(request, "线上交易需要填写收货人、电话和收货地址")
            return redirect("checkout", pk=pk)

        pay_now = mode == "online" and request.POST.get("pay") == "1"

        try:
            with transaction.atomic():
                order = Order.objects.create(
                    product=product,
                    buyer=request.user,
                    seller=product.seller,
                    price=product.price,
                    message=(request.POST.get("message") or "").strip()[:120],
                    trade_mode=mode,
                    receiver_name=receiver_name if mode == "online" else "",
                    receiver_phone=receiver_phone if mode == "online" else "",
                    address=address if mode == "online" else "",
                    shipping_fee=shipping_fee,
                    is_paid=pay_now,
                    paid_at=timezone.now() if pay_now else None,
                )
        except IntegrityError:
            messages.info(request, "你已经下过单了，去「我的订单」看看进度吧")
            return redirect("order_list")

        if pay_now:
            messages.success(request, "支付成功，已通知卖家尽快发货 🎉")
        elif mode == "face":
            messages.success(request, "已下单，等卖家确认后约个时间当面交易吧")
        else:
            messages.success(request, "订单已提交，可以在「我的订单」里完成支付")
        return redirect("order_list")

    return render(
        request,
        "checkout.html",
        {
            "product": product,
            "conversation": conv,
            "shipping_fee": product.shipping_fee_amount,
            "total_price": product.price + product.shipping_fee_amount,
        },
    )


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

        elif action == "pay" and is_buyer and order.can_pay:
            # 模拟支付：真实项目这里会跳支付渠道，回调后再改状态
            order.is_paid = True
            order.paid_at = timezone.now()
            order.save(update_fields=["is_paid", "paid_at", "updated_at"])
            messages.success(request, "支付成功，已通知卖家尽快发货 🎉")

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
