from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from atlas.api.errors import AtlasError
from atlas.api.serializers import (
    SAMPLE_DESTINATION,
    SAMPLE_ORIGIN,
    AnalysisInputSerializer,
    AnalysisSerializer,
    ErrorResponseSerializer,
    FrameQuerySerializer,
    FrameSerializer,
    GeocodeCandidateSerializer,
    GeocodeInputSerializer,
    HealthSerializer,
    ScenariosSerializer,
)
from atlas.domain import POLICY_VERSION
from atlas.services.analysis import create_analysis, get_analysis, get_frame

ERRORS = {
    400: ErrorResponseSerializer,
    401: ErrorResponseSerializer,
    404: ErrorResponseSerializer,
    409: ErrorResponseSerializer,
    410: ErrorResponseSerializer,
    413: ErrorResponseSerializer,
    429: ErrorResponseSerializer,
    503: ErrorResponseSerializer,
}


class HealthView(APIView):
    @extend_schema(responses=HealthSerializer, operation_id="health")
    def get(self, request):
        from django.conf import settings

        from atlas.services.live import live_available

        return Response(
            HealthSerializer(
                {
                    "status": "ok",
                    "assessment_access_required": bool(settings.ATLAS_ASSESSMENT_ACCESS_HASH),
                    "mode": "sample",
                    "live_available": live_available(),
                    "policy_version": POLICY_VERSION,
                    "version": "0.1.0",
                }
            ).data
        )


class ContractInfoView(APIView):
    @extend_schema(exclude=True)
    def get(self, request):
        return Response(
            {
                "mode": "sample",
                "schema_url": "/api/v1/schema/",
                "documentation": "backend/API_CONTRACT.md",
                "external_assets": False,
            }
        )


class ScenariosView(APIView):
    @extend_schema(responses=ScenariosSerializer, operation_id="scenarios")
    def get(self, request):
        data = {
            "mode": "sample",
            "sample_data": True,
            "locations": {"origin": SAMPLE_ORIGIN, "destination": SAMPLE_DESTINATION},
            "defaults": {
                "departure_at": "2026-10-10T11:00:00Z",
                "departure_local": "2026-10-10T06:00:00",
                "departure_fold": None,
                "origin_timezone": "America/Chicago",
                "load_weight_lb": "24000",
                "checkpoint_interval_miles": 25,
            },
            "scenarios": [
                {
                    "id": "complete",
                    "label": "Complete sample",
                    "description": "Three authored routes with complete checkpoint conditions.",
                },
                {
                    "id": "partial",
                    "label": "Partial forecast",
                    "description": "Missing required snow depth after the illustrative six-hour window; no verified recommendation.",
                },
                {
                    "id": "no-travel",
                    "label": "No Travel",
                    "description": "Known wind blockers on every authored route; no recommended route.",
                },
            ],
        }
        return Response(ScenariosSerializer(data).data)


class AnalysisCreateView(APIView):
    @extend_schema(
        request=AnalysisInputSerializer,
        responses={201: AnalysisSerializer, **ERRORS},
        operation_id="createAnalysis",
    )
    def post(self, request):
        if (
            isinstance(request.data, dict)
            and isinstance(request.data.get("mode"), str)
            and request.data.get("mode") in {"live", "actual"}
        ):
            from atlas.services.live import require_live

            require_live()
        serializer = AnalysisInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        snapshot = create_analysis(serializer.validated_data)
        return Response(AnalysisSerializer(snapshot.result).data, status=201)


class AnalysisDetailView(APIView):
    @extend_schema(responses={200: AnalysisSerializer, **ERRORS}, operation_id="getAnalysis")
    def get(self, request, analysis_id):
        return Response(AnalysisSerializer(get_analysis(analysis_id).result).data)


class FrameView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                "hour",
                int,
                required=True,
                description="Integer offset 0 through 48 from the stored departure.",
            ),
            OpenApiParameter("variable", str, required=True, enum=["wind", "rain", "snow"]),
        ],
        responses={200: FrameSerializer, **ERRORS},
        operation_id="getFrame",
    )
    def get(self, request, analysis_id):
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise AtlasError(
                "VALIDATION_ERROR", "Each frame query parameter must occur exactly once."
            )
        query = FrameQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        snapshot = get_analysis(analysis_id)
        return Response(FrameSerializer(get_frame(snapshot, **query.validated_data)).data)


class GeocodeView(APIView):
    @extend_schema(
        request=GeocodeInputSerializer,
        responses={200: GeocodeCandidateSerializer(many=True), **ERRORS},
        operation_id="geocodeLocations",
    )
    def post(self, request):
        from atlas.services.live import geocode

        query = GeocodeInputSerializer(data=request.data)
        query.is_valid(raise_exception=True)
        return Response(
            GeocodeCandidateSerializer(geocode(query.validated_data["text"]), many=True).data
        )
