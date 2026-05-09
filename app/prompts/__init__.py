"""Plantillas Jinja2 versionadas para los prompts del estimador.

Cada versión vive en su propio subdirectorio (``v1/``, ``v2/`` …) con los
mismos tres ficheros: ``system.j2``, ``user.j2`` y ``examples.j2``.

Punto de entrada público:

>>> from app.prompts.loader import render_estimation_prompt
"""
