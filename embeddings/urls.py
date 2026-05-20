from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("api/embed/run/", views.run_embed, name="embeddings_run"),
    path("api/embed/jobs/", views.create_embedding_job, name="embeddings_job_create"),
    path(
        "api/embed/jobs/<uuid:public_id>/requeue/",
        views.requeue_embedding_job,
        name="embeddings_job_requeue",
    ),
    path(
        "api/embed/jobs/<uuid:public_id>/run/",
        views.run_embedding_job_by_id,
        name="embeddings_job_run",
    ),
    path("api/embed/jobs/<uuid:public_id>/", views.get_embedding_job, name="embeddings_job_detail"),
    path("api/embed/path-help/", views.embed_path_help, name="embeddings_path_help"),
]
