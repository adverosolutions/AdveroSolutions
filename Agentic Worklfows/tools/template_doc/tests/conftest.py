"""The doc tools are plain scripts that import each other by module name
(``from parse_doc import ...``), so their folder goes on sys.path here."""
import os
import sys

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
