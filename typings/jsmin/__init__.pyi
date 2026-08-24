# Partial stub -- only symbols used in this project.

import io

class JavascriptMinify:
    def __init__(
        self,
        instream: io.StringIO = ...,
        outstream: io.StringIO = ...,
        quote_chars: str = ...,
    ) -> None: ...
    def minify(
        self, instream: io.StringIO = ..., outstream: io.StringIO = ...
    ) -> None: ...
