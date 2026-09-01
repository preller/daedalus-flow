"""Sphinx configuration for the daedalus-flow documentation build."""

from __future__ import annotations

from importlib.metadata import version as _v

project = "daedalus-flow"
author = "Patricio Reller"
copyright = "2026, University College London"
release = _v("daedalus-flow")  # hatch-vcs; no hardcoded version
version = release

# sphinxcontrib.typer renders the dae CLI as text in reference/cli.md; the html
# and png renders need a browser and would break the hermetic RTD build.
extensions = [
    "myst_parser",
    "autoapi.extension",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.typer",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinxcontrib.mermaid",
    "sphinx_llms_txt",
    "sphinxext.opengraph",
    "notfound.extension",
]

source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "substitution",
    "tasklist",
    "attrs_inline",
]
myst_heading_anchors = 3  # so [](file.md#heading) links resolve

# AutoAPI parses flow/ statically. _api.py must stay visible so the __init__
# re-exports (FlowContext, Role, entry) resolve; core/ and cli/ are left out.
autoapi_dirs = ["../src/daedalus/flow"]
autoapi_root = "api"
autoapi_type = "python"
autoapi_options = [
    "members",
    "imported-members",
    "show-inheritance",
    "show-module-summary",
]
autoapi_ignore: list[str] = []
autoapi_member_order = "groupwise"
autoapi_python_class_content = "both"
autoapi_keep_files = False
autoapi_add_toctree_entry = False  # reference/index.md lists the API page
autoapi_own_page_level = "class"

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "scipy": ("https://docs.scipy.org/doc/scipy/", None),
    "astropy": ("https://docs.astropy.org/en/stable/", None),
    "networkx": ("https://networkx.org/documentation/stable/", None),
}

html_theme = "shibuya"
html_title = "daedalus-flow"
html_baseurl = "https://daedalus-flow.readthedocs.io/en/latest/"
html_theme_options = {
    "accent_color": "violet",
    "color_mode": "auto",
    "globaltoc_expand_depth": 1,
}
html_context = {  # the edit-this-page button
    "source_type": "github",
    "source_user": "preller",
    "source_repo": "daedalus-flow",
    "source_version": "main",
    "source_docs_path": "/docs/",
}

ogp_site_url = "https://daedalus-flow.readthedocs.io/en/latest/"
ogp_description_length = 200
ogp_enable_meta_description = True

# Strip prompts so pasted commands are clean.
copybutton_prompt_text = r">>> |\.\.\. |\$ |dae "
copybutton_prompt_is_regex = True
copybutton_only_copy_prompt_lines = False

llms_txt_full_filename = "llms-full.txt"

# Client-side mermaid.js; the png and svg outputs shell out to a headless browser.
mermaid_version = "11.4.1"
# Natural size capped at the column width. The plugin's default 500px box
# and 100% width scale small diagrams up and float them in blank space.
mermaid_width = "fit-content"
mermaid_height = "auto"
# One palette for both colour modes, read from shibuya's CSS variables when the
# svg renders. The "&" rule cancels the theme's dark-mode inversion filter.
mermaid_init_config = {
    "startOnLoad": False,
    "flowchart": {
        "useMaxWidth": False,
        "curve": "basis",
        "padding": 12,
        "nodeSpacing": 30,
        "rankSpacing": 40,
    },
    "themeVariables": {"fontFamily": "var(--sy-f-text)", "fontSize": "16px"},
    "themeCSS": " ".join(
        [
            "& { filter: none; }",
            ".node rect, .node circle, .node ellipse, .node polygon, .node path"
            " { fill: var(--accent-3); stroke: var(--accent-7); stroke-width: 1px; }",
            ".cluster rect { fill: var(--sy-c-surface); stroke: var(--sy-c-border); }",
            ".label, .label span, .nodeLabel, .edgeLabel { color: var(--sy-c-text); }",
            ".label text { fill: var(--sy-c-text); }",
            ".cluster-label span, .cluster span { color: var(--sy-c-light); }",
            ".cluster-label text, .cluster text { fill: var(--sy-c-light); }",
            ".edgePath .path, .flowchart-link"
            " { stroke: var(--sy-c-light); stroke-width: 1.5px; }",
            ".marker, .arrowheadPath { fill: var(--sy-c-light); stroke: var(--sy-c-light); }",
            ".edgeLabel, .edgeLabel p, .labelBkg { background-color: var(--sy-c-background); }",
        ]
    ),
}

# nitpicky with -W would fail on the typing xrefs AutoAPI emits.
nitpicky = False

# linkcheck runs outside the -W gate; the project's own URLs 404 until release.
linkcheck_ignore = [
    r"https://github\.com/preller/.*",
    r"https://daedalus-flow\.readthedocs\.io/.*",
]

# Pygments has no jsonc lexer; alias it to JSON for reference/json-envelope.md.
from pygments.lexers.data import JsonLexer as _JsonLexer  # noqa: E402
from sphinx.highlighting import lexers as _lexers  # noqa: E402

_lexers["jsonc"] = _JsonLexer()
