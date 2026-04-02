import requests
import urllib.parse

def search_web(query: str, max_results: int = 3) -> str:
    """
    Voert een kennis-zoekopdracht uit via de Wikipedia API.
    Dit levert gestructureerde, schone tekst op zonder HTML-vervuiling.
    """
    # Configuratie
    user_agent = "WintripAgent/1.0 (Local-First macOS AI Agent; contact: philip@wintrip.ai)"
    headers = {"User-Agent": user_agent}
    
    # We gebruiken de Wikipedia OpenSearch API (Nederlands)
    # Formaat: [query, [titels], [samenvattingen], [links]]
    encoded_query = urllib.parse.quote(query)
    api_url = f"https://nl.wikipedia.org/w/api.php?action=opensearch&search={encoded_query}&limit={max_results}&namespace=0&format=json"
    
    try:
        # Request uitvoeren met timeout
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Data extractie uit Wikipedia OpenSearch formaat
        # data[0] = originele query
        titles = data[1]
        summaries = data[2]
        links = data[3]
        
        if not titles:
            return f"[WEB SEARCH] Geen resultaten gevonden voor de zoekopdracht: '{query}'."
            
        # Formatteer de resultaten naar een schone tekst-string
        output_lines = [f"--- Web Search Resultaten voor '{query}' ---"]
        
        for i in range(len(titles)):
            title = titles[i]
            summary = summaries[i] if i < len(summaries) and summaries[i] else "Geen samenvatting beschikbaar."
            link = links[i] if i < len(links) else "Geen link beschikbaar."
            
            result_item = (
                f"\n[{i+1}] TITEL: {title}\n"
                f"    SAMENVATTING: {summary}\n"
                f"    BRON: {link}"
            )
            output_lines.append(result_item)
            
        return "\n".join(output_lines)
        
    except requests.exceptions.ConnectionError:
        return "[WEB SEARCH FOUT] Kan geen verbinding maken met het internet."
    except requests.exceptions.Timeout:
        return "[WEB SEARCH FOUT] De zoekopdracht duurde te lang (timeout)."
    except Exception as e:
        return f"[WEB SEARCH FOUT] Onverwachte fout bij het ophalen van resultaten: {str(e)}"

if __name__ == "__main__":
    # Testcase voor validatie
    print("Test: Zoeken naar 'SwiftUI'...")
    resultaat = search_web("SwiftUI", max_results=2)
    print(resultaat)
    
    print("\nTest: Zoeken naar iets onbekends...")
    print(search_web("xyz_onbekend_term_123"))
