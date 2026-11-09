"""
Django settings for config project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录：线上通过 XJ_DATA_DIR 指向「发布目录之外」的持久目录，
# 这样重新发布（覆盖源码目录）时，用户数据与上传的图片不会被冲掉。
DATA_DIR = Path(os.environ.get("XJ_DATA_DIR") or BASE_DIR)

# 线上可用环境变量覆盖；默认值为本地开发用，不影响现有部署
SECRET_KEY = os.environ.get("XJ_SECRET_KEY") or 'django-insecure-_hy(+)%&1wcs3_80kuyxb4whdj%xwxxp23uqy31i63258fohut'

# 保持 DEBUG 开启：当前媒体图片由 runserver 的静态服务直接提供（见 config/urls.py），
# 关闭后线上商品图会 404。正式上生产时应改由 Nginx 托管 MEDIA_ROOT 并关闭 DEBUG。
DEBUG = True

ALLOWED_HOSTS = ['*']

# 站点部署在反向代理后面，浏览器发来的 Origin 是公网域名，
# 必须显式加入受信任来源，否则所有 POST（登录/注册/下单）都会被 CSRF 拦截。
# 换域名时设置 XJ_CSRF_ORIGINS 即可，多个来源用英文逗号分隔。
_csrf_origins = os.environ.get("XJ_CSRF_ORIGINS") or "https://xianxiaoji-market.app.workbuddy.host"
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",") if o.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 项目应用
    'accounts',
    'goods',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # 导航栏未读消息红点
                'goods.context_processors.chat_notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# 数据库：开发阶段先用 SQLite 零配置跑起来，上线/联调阶段切换 MySQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# 自定义用户模型
AUTH_USER_MODEL = 'accounts.User'

# 登录相关跳转
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = 'media/'
MEDIA_ROOT = DATA_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
