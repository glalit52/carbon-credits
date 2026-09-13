"""The dashboard.

A single self-contained HTML file with the data inlined, built from a stored
analysis. No bundler, no framework, no network at load: the page opens from a
file:// URL on a laptop with no internet and renders the same thing it renders
on the deployed site.

That constraint is not minimalism for its own sake. The dashboard's job is to
answer "what needs my attention" in the seconds a person actually gives it, and
every dependency between the data and the pixels is somewhere that can fail
and leave a wealth summary half-rendered.
"""

from __future__ import annotations

from .build import build, build_payload

__all__ = ["build", "build_payload"]
