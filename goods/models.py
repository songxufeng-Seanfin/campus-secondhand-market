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

    # 邮寄规则由卖家发布时预先设定，线上交易时据此计算运费
    SHIPPING_CHOICES = [
        ("free", "包邮"),
        ("paid", "不包邮（运费买家承担）"),
    ]
    # 不包邮时的统一校内寄件运费，实际项目里可以按地区/重量算
    PAID_SHIPPING_FEE = 8

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
    shipping_policy = models.CharField(
        "邮寄方式", max_length=6, choices=SHIPPING_CHOICES, default="free"
    )
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

    @property
    def is_free_shipping(self):
        return self.shipping_policy == "free"

    @property
    def shipping_fee_amount(self):
        """线上交易时的运费：包邮为 0，不包邮取统一运费。"""
        return 0 if self.is_free_shipping else self.PAID_SHIPPING_FEE


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

    # ---- 交易方式：面对面 / 线上 ----
    TRADE_MODE_CHOICES = [
        ("face", "面对面交易"),
        ("online", "线上交易"),
    ]
    trade_mode = models.CharField(
        "交易方式", max_length=8, choices=TRADE_MODE_CHOICES, default="face"
    )
    # 线上交易才需要收货信息；面对面交易留空
    receiver_name = models.CharField("收货人", max_length=20, blank=True)
    receiver_phone = models.CharField("联系电话", max_length=20, blank=True)
    address = models.CharField("收货地址", max_length=120, blank=True)
    shipping_fee = models.DecimalField(
        "运费（元）", max_digits=6, decimal_places=2, default=0
    )
    is_paid = models.BooleanField("已支付", default=False)
    paid_at = models.DateTimeField("支付时间", blank=True, null=True)

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
    def is_online(self):
        return self.trade_mode == "online"

    @property
    def total_price(self):
        """线上交易需付总额 = 商品价 + 运费；面对面交易就是商品价。"""
        return self.price + (self.shipping_fee or 0)

    @property
    def can_pay(self):
        """线上订单、未支付、还在进行中，才显示支付按钮。"""
        return self.is_online and not self.is_paid and self.is_active

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

    # ---- 评价相关：模板和视图共用的小工具 ----
    @property
    def can_be_rated(self):
        """只有走完流程的订单才有资格被评价。"""
        return self.status == "completed"

    def rating_by(self, user):
        """user 在这笔订单里已经提交的评价（没评过则 None）。"""
        if not user.is_authenticated:
            return None
        return self.ratings.filter(rater=user).first()

    def can_rate(self, user):
        """user 能否评价这笔订单：订单已完成、user 是买卖双方之一、还没评过。"""
        if not self.can_be_rated or not user.is_authenticated:
            return False
        return user.id in (self.buyer_id, self.seller_id) and self.rating_by(user) is None


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


class Conversation(models.Model):
    """买卖双方围绕某件商品的一对一会话。

    一个买家对一件商品只会有一个会话（唯一约束保证），
    点「我想要」和「直接购买」进的是同一个会话，避免同一件商品被拆成多条聊天。
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="conversations", verbose_name="商品"
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations_as_buyer",
        verbose_name="买家",
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations_as_seller",
        verbose_name="卖家",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("最后活跃", auto_now=True)

    class Meta:
        verbose_name = "私聊会话"
        verbose_name_plural = "私聊会话"
        # 最近有新消息的排前面
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["buyer", "-updated_at"]),
            models.Index(fields=["seller", "-updated_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "buyer"], name="uniq_conversation_product_buyer"
            )
        ]

    def __str__(self):
        return f"{self.buyer} ↔ {self.seller} · {self.product.title}"

    @property
    def last_message(self):
        return self.chat_messages.last()

    def other_party(self, user):
        """会话里的另一方，模板上显示对方的昵称。"""
        return self.seller if user.id == self.buyer_id else self.buyer

    def unread_count_for(self, user):
        """给对方算未读数：别人发给我、我还没点开的。"""
        return self.chat_messages.filter(is_read=False).exclude(sender=user).count()

    def can_access(self, user):
        return user.is_authenticated and user.id in (self.buyer_id, self.seller_id)


class ChatMessage(models.Model):
    """会话消息。

    is_read 由接收方打开会话时批量置为 True，
    导航栏的未读红点就靠它算，不需要额外的通知表。
    """

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="chat_messages", verbose_name="会话"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_messages",
        verbose_name="发送者",
    )
    body = models.CharField("内容", max_length=300)
    is_read = models.BooleanField("已读", default=False)
    created_at = models.DateTimeField("发送时间", auto_now_add=True)

    class Meta:
        verbose_name = "会话消息"
        verbose_name_plural = "会话消息"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return f"{self.sender}: {self.body[:20]}"


class Rating(models.Model):
    """交易评价：订单完成后，买家和卖家各给对方打一次 1-5 星分。

    设计要点：
    - 评价挂在订单上而不是商品上：一笔成交产生两条互评（买家评卖家、卖家评买家）；
    - UniqueConstraint(order, rater) 从数据库层面保证每人每单只能评一次；
    - 不给用户存冗余信用字段，好评率/均分实时聚合计算，避免双写不一致；
    - rater/ratee 的合法性（必须是该订单买卖双方）在视图里校验，模型层不重复约束。
    """

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="ratings", verbose_name="订单"
    )
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ratings_given",
        verbose_name="评价人",
    )
    ratee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ratings_received",
        verbose_name="被评价人",
    )
    SCORE_CHOICES = [(i, f"{i} 星") for i in range(1, 6)]
    score = models.PositiveSmallIntegerField("评分", choices=SCORE_CHOICES)
    content = models.CharField("评价内容", max_length=200, blank=True)
    created_at = models.DateTimeField("评价时间", auto_now_add=True)

    class Meta:
        verbose_name = "交易评价"
        verbose_name_plural = "交易评价"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["order", "rater"], name="uniq_rating_order_rater")
        ]
        indexes = [models.Index(fields=["ratee", "-created_at"])]

    def __str__(self):
        return f"{self.rater} → {self.ratee} · {self.score}星"

    @property
    def is_buyer_rater(self):
        """买家评卖家为 True，卖家评买家为 False，主页上用于显示角色标签。"""
        return self.rater_id == self.order.buyer_id
