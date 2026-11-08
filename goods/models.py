from django.conf import settings
from django.db import models
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
