"""商品相关的模板过滤器。

分类在数据库里存的是 emoji 图标，但界面上我们希望统一使用
Bootstrap Icons 的线性图标（颜色跟随文字，不会跳出一堆彩色）。
所以这里按分类 slug 做一层映射，模板里用 `{{ cat.slug|cat_icon }}`。
"""

from django import template

register = template.Library()

# slug -> Bootstrap Icons 类名（均为 outline 线性图标）
ICON_MAP = {
    "books": "bi-book",
    "digital": "bi-laptop",
    "sports": "bi-bicycle",
    "life": "bi-cup-hot",
    "fashion": "bi-handbag",
    "music": "bi-music-note-beamed",
}

DEFAULT_ICON = "bi-box-seam"


@register.filter
def cat_icon(slug):
    """把分类 slug 映射成线性图标类名。"""
    return ICON_MAP.get(slug, DEFAULT_ICON)
