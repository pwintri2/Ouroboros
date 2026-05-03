import threading
from typing import Dict, Any, List

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
        return cls._instance

    def subscribe(self, frequency: float, callback: Any) -> None:
        """Abonneert een callback op een specifieke broadcast-frequentie."""
        if frequency not in self._subscribers:
            self._subscribers[frequency] = []
        self._subscribers[frequency].append(callback)

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
        for callback in self.network._subscribers.get(frequency, []):
            callback(message)
