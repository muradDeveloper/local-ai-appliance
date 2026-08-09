"""
title: Image Input Probe
author: Murad
description: Diagnostic -- inspects __messages__ to find an uploaded image and reports its raw format (data URI vs URL, mime, size). Throwaway, used to build the photo restyle tool.
requirements:
version: 0.1.0
"""

from typing import Awaitable, Callable, Optional, TypedDict


class _ImageUrl(TypedDict, total=False):
    url: str


class _ContentPart(TypedDict, total=False):
    type: str
    image_url: _ImageUrl


class _Message(TypedDict, total=False):
    role: str
    content: "str | list[_ContentPart]"


class Tools:
    def __init__(self) -> None:
        pass

    async def probe_uploaded_image(
        self,
        __messages__: Optional[list[_Message]] = None,
        __event_emitter__: Optional[Callable[..., Awaitable[None]]] = None,
    ) -> str:
        """
        Inspect the most recently uploaded image in the conversation and report its raw format for debugging; use whenever the user asks to probe, inspect, or debug an uploaded image
        """
        lines: list[str] = []
        msgs: list[_Message] = __messages__ or []
        lines.append(f"messages received: {len(msgs)}")

        # Walk newest -> oldest; stop at the first message that carries image parts.
        found: list[tuple[int, str, str]] = []
        for idx in range(len(msgs) - 1, -1, -1):
            m = msgs[idx]
            role = m.get("role", "?")
            content = m.get("content")
            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "image_url":
                        image_url = part.get("image_url")
                        url = image_url.get("url", "") if image_url else ""
                        found.append((idx, role, url))
            if found:
                break

        lines.append(f"images in newest image-bearing message: {len(found)}")
        for i, (idx, role, url) in enumerate(found):
            if url.startswith("data:"):
                comma = url.find(",")
                header = url[:comma] if comma != -1 else url[:40]
                b64_chars = len(url) - (comma + 1) if comma != -1 else 0
                lines.append(
                    f"  [{i}] msg#{idx} role={role} kind=data-uri header='{header}' base64_chars={b64_chars}"
                )
            else:
                lines.append(f"  [{i}] msg#{idx} role={role} kind=url value='{url[:160]}'")

        # If nothing found, dump the shape of the last few messages to aid debugging.
        if not found:
            for idx in range(len(msgs) - 1, max(-1, len(msgs) - 4), -1):
                m = msgs[idx]
                ctype = type(m.get("content")).__name__
                lines.append(f"  msg#{idx} role={m.get('role', '?')} content_type={ctype}")

        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Image probe complete", "done": True}}
            )

        return "IMAGE PROBE RESULT:\n" + "\n".join(lines)
