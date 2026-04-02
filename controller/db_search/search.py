from typing import List, Dict
from db_search import models
from db_search.models import register_function

@register_function(
    name="chromadb.search",
    description="Search for records in the ChromaDB database"
)
def search(
    session: models.Session,
    params: Dict[str, str],
    page: int = 1,
    per_page: int = 10
) -> List[Dict[str, str]]:
    """
    Search for records in the ChromaDB database based on user-provided search criteria.
    """
    try:
        # Step 2: Parse Search Parameters
        # Using .get() to avoid KeyError if parameters are missing
        artist_name = params.get('artist_name')
        song_title = params.get('song_title')
        album_title = params.get('album_title')
        genre = params.get('genre')
        release_date = params.get('release_date')

        # Step 3: Construct Search Query
        query = session.query(models.Record)
        if artist_name:
            query = query.filter(models.Record.artist_name == artist_name)
        if song_title:
            query = query.filter(models.Record.song_title == song_title)
        if album_title:
            query = query.filter(models.Record.album_title == album_title)
        if genre:
            query = query.filter(models.Record.genre == genre)
        if release_date:
            query = query.filter(models.Record.release_date == release_date)

        # Step 4: Apply Pagination
        # Standard SQLAlchemy uses offset and limit for pagination
        results = query.offset((page - 1) * per_page).limit(per_page).all()

        # Step 5: Map Search Results
        result_map = {
            'id': lambda x: x.id,
            'artist_name': lambda x: x.artist_name,
            'song_title': lambda x: x.song_title,
            'album_title': lambda x: x.album_title,
            'genre': lambda x: x.genre,
            'release_date': lambda x: x.release_date
        }

        # Step 6: Return Search Results
        # Mapping each record to a dictionary using the result_map lambdas
        return [{k: v(record) for k, v in result_map.items()} for record in results]

    except Exception as e:
        # Step 7: Handle Errors
        print(f"Error: {e}")
        return []
