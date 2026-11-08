"""演示数据命令：`python manage.py seed_demo`

作用：
1. 建立 6 个商品分类；
2. 创建 3 个演示用户；
3. 生成 8 件演示商品，并用 Pillow 动态画封面图（无需手动找素材）。

设计成管理命令（而不是一次性脚本）的好处：可重复执行、幂等（get_or_create），
队友拉下代码后跑一条命令就有完整演示数据。
"""

from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from goods.models import Category, Product

# 商品 → 演示实拍图（放在 goods/seed_images/ 下，1120x840 的 4:3 图片）
IMAGE_MAP = {
    "高等数学 同济第七版 上下册": "gaoshu.jpg",
    "iPad Air 4 64G 深空灰": "ipad.jpg",
    "捷安特 通勤自行车 24 寸": "bike.jpg",
    "宿舍桌面迷你冰箱": "fridge.jpg",
    "雅马哈 F310 民谣吉他": "guitar.jpg",
    "索尼 WH-1000XM4 头戴降噪耳机": "headphones.jpg",
    "考研英语真题 + 词汇书（一整套）": "english.jpg",
    "斯伯丁 7 号篮球": "basketball.jpg",
}

DEMO_PASSWORD = "xj" + "2026demo"

CATEGORIES = [
    ("教材书籍", "books", "📚", 1),
    ("数码电子", "digital", "💻", 2),
    ("运动出行", "sports", "🚲", 3),
    ("生活用品", "life", "🛏️", 4),
    ("服饰鞋包", "fashion", "👕", 5),
    ("乐器爱好", "music", "🎸", 6),
]

# 每件商品：(标题, 分类slug, 售价, 原价, 成色, 地点, 描述, 卖家序号)
PRODUCTS = [
    (
        "高等数学 同济第七版 上下册",
        "books", "25", "89", "good", "白云校区 · 图书馆门口",
        "大一用过，笔记写在便签上，可以撕掉。书角有点磨损，内页干净无缺页。"
        "配套的习题册也一起送，考研复习刚好用得上。",
        0,
    ),
    (
        "iPad Air 4 64G 深空灰",
        "digital", "1800", "4399", "like_new", "白云校区 · 宿舍楼下",
        "2023 年买的，一直贴膜带壳用，屏幕无划痕，电池健康 92%。"
        "原装充电器+数据线都在，盒子也留着。换新机了所以出。",
        1,
    ),
    (
        "捷安特 通勤自行车 24 寸",
        "sports", "380", "899", "good", "白云校区 · 南门车棚",
        "骑了一年多，链条上个月刚换新，刹车灵敏。车筐和后座都在，"
        "适合校园通勤。毕业了带不走，低价出给学弟学妹。",
        2,
    ),
    (
        "宿舍桌面迷你冰箱",
        "life", "120", "299", "good", "白云校区 · 3 栋 402",
        "容量 12L，放饮料和面膜刚好，制冷正常无异响。"
        "毕业清宿舍，自提优先，可以帮忙搬到楼下。",
        0,
    ),
    (
        "雅马哈 F310 民谣吉他",
        "music", "520", "1080", "like_new", "白云校区 · 音乐社活动室",
        "大一入社买的，弹了半年就吃灰了。琴颈无变形，音准正常，"
        "送琴包、变调夹、备用弦一套。想学的同学别买新的了。",
        1,
    ),
    (
        "索尼 WH-1000XM4 头戴降噪耳机",
        "digital", "950", "2299", "like_new", "白云校区 · 图书馆门口",
        "降噪很顶，自习室神器。耳罩无脱皮，功能全正常，"
        "附收纳包和音频线。因为换了入耳式所以出。",
        2,
    ),
    (
        "考研英语真题 + 词汇书（一整套）",
        "books", "30", "128", "good", "白云校区 · 一教大厅",
        "黄皮书真题 2010-2023，做过一部分（铅笔写的，已擦）。"
        "词汇书是恋练有词，笔记很全，适合接手继续用。",
        0,
    ),
    (
        "斯伯丁 7 号篮球",
        "sports", "60", "160", "fair", "白云校区 · 篮球场",
        "室外场打了半年，表皮有磨损但不影响手感，气足不漏。"
        "换个新的所以出，学生党练球够用了。",
        1,
    ),
]

# 封面配色：按分类区分，避免所有图长得一样
PALETTE = {
    "books": ("#e8f3ff", "#bcdcff", "#1677ff"),
    "digital": ("#eef2ff", "#c7d2fe", "#4f46e5"),
    "sports": ("#e8fff5", "#b7f0d8", "#0e8a63"),
    "life": ("#fff7e6", "#ffe1a8", "#d48806"),
    "fashion": ("#fff0f6", "#ffd6e7", "#c2185b"),
    "music": ("#f6f0ff", "#ddd0ff", "#7048e8"),
}


def _make_cover(title: str, slug: str) -> ContentFile:
    """用 Pillow 画一张渐变封面：底色渐变 + 白色圆角卡片 + 标题文字。"""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 800, 600
    light, mid, deep = PALETTE.get(slug, ("#e8f3ff", "#bcdcff", "#1677ff"))
    img = Image.new("RGB", (width, height), light)
    draw = ImageDraw.Draw(img)

    # 1. 对角线渐变：从浅色过渡到中间色
    c1 = tuple(int(light[i : i + 2], 16) for i in (1, 3, 5))
    c2 = tuple(int(mid[i : i + 2], 16) for i in (1, 3, 5))
    for y in range(height):
        ratio = y / height
        color = tuple(int(c1[i] + (c2[i] - c1[i]) * ratio) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)

    # 2. 半透明白色圆角卡片（营造层次）
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(card)
    cdraw.rounded_rectangle(
        (70, 120, width - 70, height - 120), radius=36, fill=(255, 255, 255, 205)
    )
    img = Image.alpha_composite(img.convert("RGBA"), card).convert("RGB")
    draw = ImageDraw.Draw(img)

    # 3. 标题文字：按长度自动换行、自动缩小字号
    text_color = tuple(int(deep[i : i + 2], 16) for i in (1, 3, 5))
    font = None
    for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        try:
            font = ImageFont.truetype(path, 46)
            break
        except OSError:
            continue
    if font is None:  # 没有中文字体时退化为英文，仍可生成
        font = ImageFont.load_default()

    # 简单按字符数折行：每行 12 个字
    lines = [title[i : i + 12] for i in range(0, len(title), 12)][:3]
    total_h = len(lines) * 62
    start_y = (height - total_h) // 2
    for idx, line in enumerate(lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
        except Exception:
            w = len(line) * 46
        draw.text(((width - w) / 2, start_y + idx * 62), line, fill=text_color, font=font)

    # 4. 底部品牌水印
    draw.text((width - 150, height - 46), "闲小集", fill=text_color, font=ImageFont.load_default())

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=86)
    return ContentFile(buffer.getvalue(), name=f"{slug}-{abs(hash(title)) % 100000}.jpg")


class Command(BaseCommand):
    help = "生成演示数据：6 个分类 + 3 个演示用户 + 8 件带封面的商品"

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. 分类
        cat_map = {}
        for name, slug, icon, order in CATEGORIES:
            cat, _ = Category.objects.get_or_create(
                slug=slug, defaults={"name": name, "icon": icon, "order": order}
            )
            cat_map[slug] = cat
        self.stdout.write(f"分类就绪：{Category.objects.count()} 个")

        # 2. 演示用户
        sellers = []
        for idx, username in enumerate(["林晓雯", "陈嘉豪", "周子航"]):
            user, created = User.objects.get_or_create(
                username=username, defaults={"phone": f"1380000000{idx}"}
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            sellers.append(user)
        self.stdout.write(f"演示用户就绪：{len(sellers)} 个（演示密码见 DEMO_PASSWORD 常量）")

        # 3. 商品
        created_count = 0
        for title, slug, price, original, condition, location, desc, seller_idx in PRODUCTS:
            if Product.objects.filter(title=title).exists():
                continue
            product = Product(
                seller=sellers[seller_idx],
                category=cat_map[slug],
                title=title,
                description=desc,
                price=Decimal(price),
                original_price=Decimal(original),
                condition=condition,
                location=location,
            )
            seed_img = Path(settings.BASE_DIR) / "goods" / "seed_images" / IMAGE_MAP.get(title, "")
            if IMAGE_MAP.get(title) and seed_img.exists():
                # 有实拍图就用实拍图（读二进制包装成 Django 的 ContentFile）
                product.image.save(
                    IMAGE_MAP[title], ContentFile(seed_img.read_bytes()), save=False
                )
            else:
                product.image.save(
                    f"{slug}-{created_count}.jpg", _make_cover(title, slug), save=False
                )
            product.save()
            created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"完成：新增 {created_count} 件商品，当前商品总数 {Product.objects.count()}"
            )
        )
