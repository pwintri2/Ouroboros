import threading
from collections import deque
from typing import Any, Dict, List

class AkashicNetwork:
    """
    Singleton message broker (Pub/Sub) voor non-lokale netwerkverstrengeling.
    Zorgt voor onmiddellijke data-updates zonder vertraging in het systeem.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AkashicNetwork, cls).__new__(cls)
                cls._instance._subscribers: Dict[float, List[Any]] = {}
                cls._instance._global_state: Dict[str, Any] = {}
                cls._instance._recent_events = deque(maxlen=200)
        return cls._instance

    def subscribe(self, frequency: float, callback: Any) -> None:
        """Abonneert een callback op een specifieke broadcast-frequentie."""
        with self._lock:
            if frequency not in self._subscribers:
                self._subscribers[frequency] = []
            self._subscribers[frequency].append(callback)

    def broadcast(self, frequency: float, message: Any) -> dict[str, Any]:
        """Publiceer een bericht en routeer het direct naar subscribers."""

        event = {"frequency": float(frequency), "message": message}
        with self._lock:
            self._recent_events.append(event)
            subscribers = list(self._subscribers.get(frequency, []))
            self._global_state["last_broadcast"] = event
        for callback in subscribers:
            callback(message)
        return event

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._recent_events)[-max(1, int(limit)):]

    def reset(self) -> None:
        """Wis transient state; vooral handig voor tests."""

        with self._lock:
            self._subscribers.clear()
            self._global_state.clear()
            self._recent_events.clear()

class TelepathicNode:
    """
    Een node die onderdeel is van het non-lokale netwerk en directe verstrengeling ondersteunt.
    """
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.state: Any = None

    def update_entangled(self, entangled_node: 'TelepathicNode', state: Any) -> None:
        """
        Verandert direct (in dezelfde tick) de eigen status én de status van de verstrengelde node.
        """
        self.state = state
        # Non-lokale update: node B muteert synchroon met node A
        entangled_node.state = state

class UniverseBroadcast:
    """
    Verantwoordelijk voor macro-updates die naar het volledige systeem worden uitgestraald.
    """
    def __init__(self):
        self.network = AkashicNetwork()

    def broadcast(self, frequency: float, message: Any) -> None:
        """
        Zendt data uit op een specifieke frequentie via het Akasha veld.
        """
        self.network.broadcast(frequency, message)
