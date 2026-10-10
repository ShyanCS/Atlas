from django.conf import settings


def assessment_security(result, generator, request, public):
    """Describe public-example versus private-operation access without credentials."""
    if settings.ATLAS_ASSESSMENT_ACCESS_HASH:
        for path, operations in result.get("paths", {}).items():
            for method, operation in operations.items():
                if method in {"get", "post", "put", "patch", "delete", "head", "options"}:
                    operation["security"] = (
                        []
                        if path.endswith("/health/")
                        or (
                            settings.ATLAS_PUBLIC_EXAMPLES_ENABLED
                            and (path.endswith("/scenarios/") or "/examples/" in path)
                        )
                        else [{"AssessmentReviewer": []}]
                    )
                    if "/analyses/{" in path:
                        if settings.ATLAS_PUBLIC_EXAMPLES_ENABLED:
                            operation["security"] = [{}, {"AssessmentReviewer": []}]
                        operation["description"] = (
                            "Anonymous access is limited to server-published curated examples. "
                            "Private and live snapshots require authorized bearer access."
                        )
    return result
