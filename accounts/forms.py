from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

from .models import User


class RegisterForm(UserCreationForm):
    """注册表单：继承 Django 内置注册表单，自动获得密码校验逻辑。"""

    phone = forms.CharField(
        label="手机号",
        max_length=11,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "选填"}),
    )

    class Meta:
        model = User
        fields = ("username", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 给内置的用户名/密码字段也套上 Bootstrap 样式
        for name in ("username", "password1", "password2"):
            self.fields[name].widget.attrs.update({"class": "form-control"})
        self.fields["username"].widget.attrs.update({"placeholder": "用户名"})


class LoginForm(AuthenticationForm):
    """登录表单：套用 Bootstrap 样式，与注册页保持一致。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("username", "password"):
            self.fields[name].widget.attrs.update(
                {"class": "form-control", "placeholder": name}
            )
        self.fields["username"].widget.attrs["placeholder"] = "用户名"
        self.fields["password"].widget.attrs["placeholder"] = "密码"
