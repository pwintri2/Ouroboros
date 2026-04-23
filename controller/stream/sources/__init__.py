# controller/stream/sources/__init__.py
# Phase 7.X — Stream of Consciousness: Bronnen
# Wintrip AI | task_id: wintrip-soc-006
#
# Elke bron in deze map is een callable: () -> list[dict]
# De daemon accepteert elke callable met dit contract.
#
# Beschikbare bronnen:
#   rss.RSSSource   — RSS/Atom feed fetcher (stdlib urllib + xml)
