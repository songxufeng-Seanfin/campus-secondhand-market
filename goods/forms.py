from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
    """商品发布 / 编辑表单。

    在 ModelForm 基础上做了三件事：
    1. 给每个字段加上 Bootstrap 的 form-control / form-select 类，省去模板里手写；
    2. 价格字段加 min 校验，防止填 0 或负数；
    3. 标题/描述加 placeholder 引导文案，降低填写门槛。
    """

    class Meta:
        model = Product
        fields = [
            "title",
            "category",
            "price",
            "original_price",
            "condition",
            "image",
            "location",
            "shipping_policy",
            "description",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "一句话说清楚是什么，例如：高等数学 同济第七版 上下册",
                }
            ),
            "category": forms.Select(attrs={"class": "form-select"}),
            "price": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "eg. 25", "step": "0.01", "min": "0.01"}
            ),
            "original_price": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "选填，填了会显示折扣", "step": "0.01", "min": "0"}
            ),
            "condition": forms.Select(attrs={"class": "form-select"}),
            "shipping_policy": forms.Select(attrs={"class": "form-select"}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "location": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "选填，例如：白云校区 · 图书馆门口"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "写清楚成色、使用时长、有无划痕、配件是否齐全……越详细越容易成交",
                }
            ),
        }

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price <= 0:
            raise forms.ValidationError("价格必须大于 0 元")
        return price

    def clean(self):
        cleaned = super().clean()
        price = cleaned.get("price")
        original = cleaned.get("original_price")
        # 原价必须高于售价，否则折扣率会算成负数，展示就乱了
        if price and original and original <= price:
            self.add_error("original_price", "原价应高于售价（若没有原价可留空）")
        return cleaned
