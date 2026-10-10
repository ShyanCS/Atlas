from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from atlas.api.views import ContractInfoView

urlpatterns = [
    path("api/v1/", include("atlas.api.urls")),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", ContractInfoView.as_view(), name="docs"),
]

handler400 = "atlas.api.errors.bad_request_view"
handler404 = "atlas.api.errors.not_found_view"
handler500 = "atlas.api.errors.server_error_view"
