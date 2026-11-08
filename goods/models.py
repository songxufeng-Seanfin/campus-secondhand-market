from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse


class Category(models.Model):
    """商品分类：教材书籍、数码电子、运动出行……

    用独立表而不是写死的 choices，是为了后台能随时增删分类，
    分类筛选也能复用同一份数据（对扩展开放、对修改封闭）。
    """

    name = models.CharField("分类名", max_length=20)
    slug = models.SlugField("URL 标识", max_length=30, unique=True)
    icon = models.CharField("图标", max_length=8, default="📦")
    order = models.PositiveIntegerField("排序", default=0)

    class Meta:
        verbose_name = "商品分类"
        verbose_name_plural = "商品分类"
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class Product(models.Model):
    """二手商品。

    设计要点：
    - seller 外键关联自定义用户模型，删除用户时级联删除其商品；
    - category 用 PROTECT，避免误删分类导致商品变成“孤儿数据”；
    - 图片存到 media/products/年/月/ 下，按时间分目录，避免单目录文件过多。
    """

    CONDITION_CHOICES = [
        ("new", "全新未拆"),
        ("like_new", "几乎全新"),
        ("good", "轻微使用"),
        ("fair", "明显使用"),
    ]

    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="卖家",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="分类",
    )
    title = models.CharField("标题", max_length=60)
    description = models.TextField("宝贝描述")
    price = models.DecimalField("售价（元）", max_digits=8, decimal_places=2)
    original_price = models.DecimalField(
        "原价（元）", max_digits=8, decimal_places=2, blank=True, null=True
    )
    condition = models.CharField(
        "成色", max_length=10, choices=CONDITION_CHOICES, default="good"
    )
    image = models.ImageField("封面图", upload_to="products/%Y/%m/", blank=True, null=True)
    location = models.CharField("交易地点", max_length=40, blank=True)
    views = models.PositiveIntegerField("浏览量", default=0)
    is_active = models.BooleanField("上架中", default=True)
    is_sold = models.BooleanField("已售出", default=False)
    created_at = models.DateTimeField("发布时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "商品"
        verbose_name_plural = "商品"
        # 默认按发布时间倒序：新发布的排前面
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["category", "-created_at"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("product_detail", args=[self.pk])

    @property
    def discount_percent(self):
        """折扣百分比，用于商品卡片上的“省 xx%”角标。"""
        if self.original_price and self.original_price > self.price:
            return round((1 - self.price / self.original_price) * 100)
        return 0

    # ---- 交易状态辅助属性：模板里直接用，避免写复杂判断 ----
    @property
    def active_order(self):
        """当前占用商品的订单（待确认 / 待收货），没有则为 None。

        列表页用 Prefetch(to_attr="active_orders") 一次性取好，
        这里优先读预取结果，避免循环渲染商品卡片时产生 N+1 查询。
        """
        prefetched = getattr(self, "active_orders", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return self.orders.filter(status__in=Order.ACTIVE_STATUSES).first()

    @property
    def is_reserved(self):
        """已被下单但还没走完流程。"""
        return self.active_order is not None

    @property
    def status_label(self):
        if self.is_sold:
            return "已售出"
        if self.is_reserved:
            return "已预订"
        if not self.is_active:
            return "已下架"
        return "在售中"

    @property
    def is_on_sale(self):
        """还能不能被下单：上架、未售出、没有进行中的订单。"""
        return self.is_active and not self.is_sold and not self.is_reserved


class Order(models.Model):
    """交易订单：买家下单 → 卖家确认 → 买家收货完成。

    状态机（只有这几种合法流转，视图里逐个校验）：
        pending（待卖家确认）→ accepted（待收货）→ completed（已完成）
        pending → rejected（卖家拒绝） / cancelled（买家取消）
        accepted → cancelled（买家取消）

    设计要点：
    - price 在下单时快照保存，之后卖家改价也不会影响已成交订单；
    - 用条件唯一约束保证「同一买家对同一商品最多一个进行中订单」，
      从数据库层面防止连点两次生成两张订单。
    """

    STATUS_CHOICES = [
        ("pending", "待卖家确认"),
        ("accepted", "待收货"),
        ("completed", "已完成"),
        ("cancelled", "已取消"),
        ("rejected", "卖家已拒绝"),
    ]
    # 进行中：占用商品、阻止其他人继续下单
    ACTIVE_STATUSES = ("pending", "accepted")

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="orders", verbose_name="商品"
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders_bought",
        verbose_name="买家",
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders_sold",
        verbose_name="卖家",
    )
    price = models.DecimalField("成交价（元）", max_digits=8, decimal_places=2)
    message = models.CharField("给卖家的话", max_length=120, blank=True)
    status = models.CharField(
        "状态", max_length=12, choices=STATUS_CHOICES, default="pending"
    )
    created_at = models.DateTimeField("下单时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "订单"
        verbose_name_plural = "订单"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["buyer", "-created_at"]),
            models.Index(fields=["seller", "-created_at"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "buyer"],
                condition=Q(status__in=["pending", "accepted"]),
                name="uniq_active_order_per_buyer_product",
            )
        ]

    def __str__(self):
        return f"#{self.pk} {self.product.title} · {self.get_status_display()}"

    @property
    def is_active(self):
        return self.status in self.ACTIVE_STATUSES

    @property
    def status_style(self):
        """状态角标配色：进行中蓝、完成绿、关闭灰。"""
        return {
            "pending": "is-pending",
            "accepted": "is-accepted",
            "completed": "is-completed",
            "cancelled": "is-closed",
            "rejected": "is-closed",
        }.get(self.status, "is-closed")


class Favorite(models.Model):
    """收藏：用户与商品的多对多中间表，用唯一约束防重复收藏。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name="用户",
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="favorited_by", verbose_name="商品"
    )
    created_at = models.DateTimeField("收藏时间", auto_now_add=True)

    class Meta:
        verbose_name = "收藏"
        verbose_name_plural = "收藏"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="uniq_favorite_user_product")
        ]

    def __str__(self):
        return f"{self.user} ♥ {self.product}"


class ProductMessage(models.Model):
    """商品留言：买家和卖家在详情页公开交流，替代早期版本里“私信开发中”的占位。"""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="messages", verbose_name="商品"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_messages",
        verbose_name="留言人",
    )
    body = models.CharField("内容", max_length=200)
    created_at = models.DateTimeField("留言时间", auto_now_add=True)

    class Meta:
        verbose_name = "商品留言"
        verbose_name_plural = "商品留言"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author}: {self.body[:20]}"

    @property
    def is_seller(self):
        """卖家本人的留言加个“卖家”小标签，避免冒充。"""
        return self.author_id == self.product.seller_id
