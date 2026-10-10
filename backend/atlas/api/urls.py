from django.urls import path

from atlas.api.views import (
    AnalysisCreateView,
    AnalysisDetailView,
    FrameView,
    GeocodeView,
    HealthView,
    ScenariosView,
)

urlpatterns = [
    path("locations/geocode/", GeocodeView.as_view()),
    path("health/", HealthView.as_view()),
    path("scenarios/", ScenariosView.as_view()),
    path("analyses/", AnalysisCreateView.as_view()),
    path("analyses/<uuid:analysis_id>/", AnalysisDetailView.as_view()),
    path("analyses/<uuid:analysis_id>/frames/", FrameView.as_view()),
]
