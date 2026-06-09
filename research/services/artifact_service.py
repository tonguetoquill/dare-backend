"""
Artifact extraction — turn the fenced blocks an agent emits into typed artifacts.

Hermes returns renderable artifacts as fenced code blocks (```mermaid, ```html,
```svg, or ```json for an Excalidraw scene). We detect those and map the language
to an artifactType the frontend renderer registry understands. Non-renderable
fences (plain code, etc.) are left in the message and not promoted to artifacts.
"""

import re

_FENCE = re.compile(r"```([\w-]*)[ \t]*\n(.*?)```", re.DOTALL)

# fenced language -> artifactType (matches the FE ArtifactRenderer registry)
_LANG_TO_TYPE = {
    "mermaid": "diagram",
    "html": "html",
    "svg": "svg",
}

_TITLES = {
    "diagram": "Diagram",
    "html": "HTML artifact",
    "svg": "SVG figure",
    "excalidraw": "Excalidraw scene",
}


def extract_artifacts(text):
    """
    Return a list of {artifact_type, title, content} for each renderable fenced
    block in `text` (empty if none).
    """
    artifacts = []
    for lang, body in _FENCE.findall(text or ""):
        lang = lang.lower().strip()
        body = body.strip()
        if not body:
            continue
        artifact_type = _LANG_TO_TYPE.get(lang)
        if artifact_type is None:
            # An Excalidraw scene comes back as json with a type marker.
            if (
                lang in ("json", "")
                and '"type"' in body[:120]
                and "excalidraw" in body[:120]
            ):
                artifact_type = "excalidraw"
            else:
                continue
        artifacts.append(
            {
                "artifact_type": artifact_type,
                "title": _TITLES.get(artifact_type, artifact_type),
                "content": body,
            }
        )
    return artifacts
