from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """自定义用户模型：在 Django 内置用户基础上扩展手机号与头像。

    为什么用自定义用户模型而不是默认 User？
    项目开始阶段就确定扩展点，避免后期迁移内置用户表的高成本——
    这是 Django 官方文档推荐的最佳实践。
    """

    phone = models.CharField("手机号", max_length=11, blank=True)
    avatar = models.ImageField("头像", upload_to="avatars/", blank=True, null=True)

    def __str__(self):
        return self.username
