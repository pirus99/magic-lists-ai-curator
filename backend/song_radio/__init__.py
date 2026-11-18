"""Song Radio feature package.

A track-based radio playlist: the user searches the library for a single song,
resolves a MusicBrainz recording MBID (either from the server metadata or a
manual fallback), then expands a similar-recordings pool from ListenBrainz and
lets the AI curate the final selection.
"""