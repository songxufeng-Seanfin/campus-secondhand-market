from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProductForm
from .models import Category, Product


def _base_queryset():
    """商品列表的公共查询集：只查上架且未售出的，并预取关联对象。

    select_related 把 seller / category 一次 JOIN 出来，
    避免模板里循环渲染时产生 N+1 查询（这是 Django 性能优化第一课）。
    """
    return (
        Product.objects.filter(is_active=True, is_sold=False)
        .select_related("seller", "category")
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
    return render(request, "product_detail.html", {"product": product, "related": related})


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
        .order_by("-created_at")
    )
    return render(request, "my_products.html", {"products": products})
