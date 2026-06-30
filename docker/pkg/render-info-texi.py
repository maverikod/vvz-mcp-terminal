#!/usr/bin/env python3
"""Render GNU Texinfo from the same Markdown guide returned by MCP ``info``."""

from __future__ import annotations

import argparse
from pathlib import Path


def _escape_texinfo(text: str) -> str:
    return (
        text.replace("@", "@@")
        .replace("{", "@{")
        .replace("}", "@}")
    )


def render(markdown: str, *, version: str) -> str:
    escaped = _escape_texinfo(markdown.rstrip())
    return f"""\\input texinfo
@setfilename mcp-terminal-docker.info
@set VERSION {version}
@settitle MCP Terminal Docker Integration
@documentencoding UTF-8

@dircategory Individual utilities
@direntry
* mcp-terminal-docker: (mcp-terminal-docker). MCP Terminal Docker host integration
@end direntry

@finalout
@titlepage
@title MCP Terminal Docker Integration
@subtitle Package mcp-terminal-docker @value{{VERSION}}
@author Vasiliy Zdanovskiy
@end titlepage

@contents

@node Top
@top MCP Terminal Docker Integration

This manual is generated from the same MCP Terminal guide returned by the
MCP @code{{info}} command. Package version: @value{{VERSION}}.

@node Guide
@chapter MCP Terminal Guide

@verbatim
{escaped}
@end verbatim

@bye
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--markdown", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(
        render(args.markdown.read_text(encoding="utf-8"), version=args.version),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
