from __future__ import annotations

from django.urls import path

from discovery import views

urlpatterns = [
    path("search/", views.search_page, name="discovery_search"),
    path("api/search/chat/", views.chat_api, name="discovery_chat_api"),
    path(
        "api/search/thumb/<uuid:job_id>/<path:frame_file>",
        views.serve_thumb,
        name="discovery_thumb",
    ),
    path(
        "api/search/video/<uuid:job_id>/<str:filename>",
        views.serve_video,
        name="discovery_video",
    ),
]
