Belangrijke instructie voor AI-ontwikkelaar
Je werkt aan het project WintripAI. De ontwikkelomgeving is NIET lokaal, maar bevindt zich op een Strato VPS (87.106.137.223).

Regels voor Docker:
1. Gebruik ALTIJD de actieve Docker context 'vps-wintrip' of exporteer DOCKER_HOST="ssh://root@87.106.137.223".
2. Probeer NOOIT Docker Desktop lokaal op te starten. De macOS machine fungeert puur als client.
3. Krijg je "Operation not permitted" via bash op macOS, dan ontbreekt system wide "Full Disk Access" of moet de terminal herstart worden. In dat geval vertrouw je op de alreeds geconfigureerde ~/.docker/config via native python access.
4. Alle docker en docker compose commando's in de terminal, worden via een SSH-tunnel op host 87.106.137.223 uitgevoerd.

Regels voor Bestanden (Cloud-Native Protocol):
1. Verwijder of refactor alle hardcoded lokale macOS paden (bijv. /Users/philip/...). Gebruik altijd relatieve paden of VPS paden (/root/wintripai/).
2. Wijzigingen aan code moeten worden gesynchroniseerd (via scp of git) met de VPS voordat iteratieve scripts, services of containers worden uitgevoerd.

Verificatie:
Run ./set_vps.sh om te controleren of de verbinding met de VPS-engine nog live is en de juiste routing actief is.
