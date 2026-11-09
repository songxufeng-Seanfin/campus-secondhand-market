from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from goods import views as goods_views

urlpatterns = [
    path('admin/', admin.site.urls),
    # PWA：三个文件必须挂在站点根路径，Service Worker 的作用域才是整个站点
    path('manifest.webmanifest', goods_views.pwa_manifest, name='pwa_manifest'),
    path('sw.js', goods_views.pwa_service_worker, name='pwa_sw'),
    path('pwa/icon-<int:size>.png', goods_views.pwa_icon, name='pwa_icon'),
    # 首页与商品相关路由（首页承载商品列表）
    path('', include('goods.urls')),
    # 账号相关路由（注册/登录/登出/个人中心）
    path('', include('accounts.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
