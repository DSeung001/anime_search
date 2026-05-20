from django.urls import path

from . import views

urlpatterns = [
    # 메인 페이지, 잡 목록 보기 페이지랑 뷰 겸용
    path("", views.job_console, name="catalog_home"),
    # 장르 리스트랑 수정, 등록 기능
    path("genres/", views.genre_list, name="catalog_genre_list"),
    path("genres/new/", views.genre_new, name="catalog_genre_new"),
    path("genres/bulk-new/", views.genre_bulk_new, name="catalog_genre_bulk_new"),
    path("genres/<int:pk>/edit/", views.genre_edit, name="catalog_genre_edit"),
    # 업로드
    path("upload/", views.anime_upload, name="catalog_anime_upload"),
    # 업로드 후 영상 미리보기
    path(
        "jobs/<uuid:public_id>/preview/<str:filename>",
        views.serve_uploaded_video,
        name="catalog_job_video_preview",
    ),
    # Job 목록 페이지
    path("jobs/", views.job_console, name="catalog_jobs"),
    # Job JSON API
    # Job 목록 가져오기
    path("api/jobs/", views.job_api_list, name="catalog_job_api_list"),
    path(
        "api/jobs/<uuid:public_id>/",
        views.job_api_detail,
        name="catalog_job_api_detail",
    ),
    # Job 실행 요청하기 (워커로 자동으로 수행되는데, 이를 요청도 가능)
    path(
        "api/jobs/<uuid:public_id>/run/",
        views.job_api_run,
        name="catalog_job_api_run",
    ),
    # Job 삭제하기
    path(
        "api/jobs/<uuid:public_id>/delete/",
        views.job_api_delete,
        name="catalog_job_api_delete",
    ),
]