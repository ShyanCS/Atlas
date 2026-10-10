from django.conf import settings


def assessment_security(result, generator, request, public):
    """Keep local anonymous contracts intact; hosted schema requires reviewer access."""
    if settings.ATLAS_ASSESSMENT_ACCESS_HASH:
        for path, operations in result.get("paths", {}).items():
            for method, operation in operations.items():
                if method in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    operation["security"] = (
                        [] if path.endswith("/health/") else [{"AssessmentReviewer": []}]
                    )
    return result
