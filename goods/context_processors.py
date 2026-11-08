"""模板全局上下文：导航栏的未读消息红点。

写成 context processor 而不是在每个视图里塞变量，
是为了所有页面（包括首页、详情页）都能自动显示未读数。
"""

from django.db.models import Q

from .models import ChatMessage


def chat_notifications(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"chat_unread_total": 0}

    total = (
        ChatMessage.objects.filter(is_read=False)
        .exclude(sender=user)
        .filter(Q(conversation__buyer=user) | Q(conversation__seller=user))
        .count()
    )
    return {"chat_unread_total": total}
