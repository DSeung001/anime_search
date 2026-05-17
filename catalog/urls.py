from django.urls import path

from . import views

urlpatterns = [
    path("", views.job_console, name="catalog_home"),
    path("genres/", views.genre_list, name="catalog_genre_list"),
    path("genres/new/", views.genre_new, name="catalog_genre_new"),
    path("genres/bulk-new/", views.genre_bulk_new, name="catalog_genre_bulk_new"),
    path("genres/<int:pk>/edit/", views.genre_edit, name="catalog_genre_edit"),
    path("upload/", views.anime_upload, name="catalog_anime_upload"),
    path(
        "jobs/<uuid:public_id>/preview/<str:filename>",
        views.serve_uploaded_video,
        name="catalog_job_video_preview",
    ),
    path("jobs/", views.job_console, name="catalog_jobs"),
    path("jobs/api/jobs/", views.job_api_list, name="catalog_job_api_list"),
    path("jobs/api/run-next/", views.job_api_run_next, name="catalog_job_api_run_next"),
    path("jobs/api/run/<uuid:public_id>/", views.job_api_run, name="catalog_job_api_run"),
    path(
        "jobs/api/jobs/<uuid:public_id>/delete/",
        views.job_api_delete,
        name="catalog_job_api_delete",
    ),
]
