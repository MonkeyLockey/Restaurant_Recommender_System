import googlemaps
import time
import csv
from datetime import datetime
import os
import random
import json
import logging

logger = logging.getLogger(__name__)


class RestaurantScraper:
    def __init__(self, api_key, existing_csv_filename=None):
        logger.debug("Initializing RestaurantScraper...")
        self.gmaps = googlemaps.Client(key=api_key)
        self.restaurants_data = []
        self.api_call_count = 0
        self.processed_place_ids = set()

        if existing_csv_filename and os.path.exists(existing_csv_filename):
            logger.info(f"Loading already processed restaurant IDs from existing file '{existing_csv_filename}'...")
            try:
                with open(existing_csv_filename, 'r', newline='', encoding='utf-8-sig') as csvfile:
                    reader = csv.DictReader(csvfile)
                    if 'place_id' in reader.fieldnames:
                        for row in reader:
                            if row['place_id']:
                                self.processed_place_ids.add(row['place_id'])
                        logger.info(f"Loaded {len(self.processed_place_ids)} restaurant IDs.")
                    else:
                        logger.warning(
                            "Warning: The existing CSV file does not contain a 'place_id' column. Cannot deduplicate across runs. Please ensure the history file includes 'place_id'.")
            except Exception as e:
                logger.error(f"Error while loading IDs from CSV: {e}")
        logger.debug("RestaurantScraper initialization complete.")

    def _make_api_call(self, api_method, *args, **kwargs):
        max_retries = 5
        base_delay = 1
        for attempt in range(max_retries):
            try:
                logger.debug(f"Attempting API call: {api_method.__name__} (Attempt {attempt + 1}/{max_retries})")
                result = api_method(*args, **kwargs)
                self.api_call_count += 1
                logger.debug(f"API call successful: {api_method.__name__}, current total calls: {self.api_call_count}")
                return result
            except googlemaps.exceptions.ApiError as e:
                error_message = str(e)
                logger.warning(f"API call failed (Attempt {attempt + 1}/{max_retries}): {error_message}")
                if "OVER_QUERY_LIMIT" in error_message or "rate limit" in error_message.lower():
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Query limit reached, retrying in {delay:.2f} seconds...")
                    time.sleep(delay)
                elif "ZERO_RESULTS" in error_message:
                    logger.info("API returned ZERO_RESULTS, no results found.")
                    return None
                else:
                    logger.error(f"Google Maps API error, not retrying: {error_message}")
                    raise  # Re-raise for other types of API errors
            except Exception as e:
                logger.error(f"An unknown error occurred (Attempt {attempt + 1}/{max_retries}): {e}")
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.error(f"Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
        raise Exception(f"API call failed after {max_retries} retries.")

    def search_restaurants(self, location, radius=50000, limit=60, use_original_language=False,
                           place_types=['restaurant']):
        logger.debug(f"Entering search_restaurants function, searching for location: {location}")
        try:
            logger.info(f"Searching for places near {location}...")

            logger.info("Getting location coordinates...")
            geocode_result = self._make_api_call(self.gmaps.geocode, location)
            logger.info(f"API call count (Geocoding): {self.api_call_count}")

            if not geocode_result:
                logger.warning(f"Could not find coordinates for location: {location}.")
                return

            lat_lng = geocode_result[0]['geometry']['location']
            logger.info(f"Found coordinates: Lat={lat_lng['lat']:.4f}, Lng={lat_lng['lng']:.4f}")

            language_param = None if use_original_language else 'en'

            all_restaurants_raw = []

            for place_type in place_types:
                logger.info(f"\n  > Searching for type: {place_type}...")
                next_page_token = None
                page_num = 1
                while True:
                    logger.info(f"    > Getting page {page_num} of {place_type} nearby results...")
                    places_result = self._make_api_call(
                        self.gmaps.places_nearby,
                        location=lat_lng,
                        radius=radius,
                        type=place_type,
                        language=language_param,
                        page_token=next_page_token
                    )
                    logger.info(f"API call count (Places Nearby): {self.api_call_count}")

                    if not places_result:
                        logger.info(f"    > No more nearby {place_type} results.")
                        break

                    current_page_restaurants = places_result.get('results', [])
                    all_restaurants_raw.extend(current_page_restaurants)
                    logger.info(f"    > Found {len(current_page_restaurants)} {place_type} on current page.")
                    logger.info(f"    > Currently collected {len(all_restaurants_raw)} places (with duplicates, all types).")

                    next_page_token = places_result.get('next_page_token')

                    if not next_page_token or page_num >= 3:  # Google Places API typically returns up to 3 pages (60 results)
                        logger.info(f"    > No next page token for {place_type} or page limit reached.")
                        break
                    else:
                        logger.info(f"    > Found next page token for {place_type}, waiting before continuing...")
                        time.sleep(2)
                    page_num += 1

            unique_ids_in_current_run = set()
            restaurants_to_process_final = []
            for restaurant in all_restaurants_raw:
                place_id = restaurant.get('place_id')
                # Ensure place_id exists and has not been processed
                if place_id and \
                        place_id not in self.processed_place_ids and \
                        place_id not in unique_ids_in_current_run:
                    restaurants_to_process_final.append(restaurant)
                    unique_ids_in_current_run.add(place_id)

            # Limit the final number of places to process to match the set limit
            restaurants_to_process = restaurants_to_process_final[:limit]

            logger.info(f"\nFound and will process details for {len(restaurants_to_process)} new unique places from {location}...")
            if not restaurants_to_process:
                logger.info(f"No new places to process in this area.")
                return

            for i, restaurant in enumerate(restaurants_to_process, 1):
                place_id = restaurant.get('place_id')
                if not place_id:
                    logger.warning(f"Warning: Place {restaurant.get('name', 'N/A')} is missing a place_id, skipping detail retrieval.")
                    continue

                logger.info(
                    f"  > [{i}/{len(restaurants_to_process)}] Processing new place: {restaurant.get('name', 'N/A')} (ID: {place_id})...")
                restaurant_info = self.get_restaurant_details(restaurant, use_original_language)
                if restaurant_info:
                    restaurant_info['place_id'] = place_id  # Place ID is already in details, but re-ensure it
                    self.restaurants_data.append(restaurant_info)
                    self.processed_place_ids.add(place_id)
                    logger.info(f"  > Successfully retrieved and stored: {restaurant_info['name']}")
                else:
                    logger.warning(f"  > Could not retrieve details for place {restaurant.get('name', 'N/A')}.")

                time.sleep(1)  # Brief delay to avoid rate limiting

        except Exception as e:
            logger.error(f"Error occurred while searching for places: {e}", exc_info=True)  # exc_info=True prints the full traceback
            logger.error(f"Current API call count: {self.api_call_count}")
        logger.debug(f"Exiting search_restaurants function, processed location: {location}")

    def get_restaurant_details(self, restaurant, use_original_language=False):
        logger.debug(f"Entering get_restaurant_details function, processing place: {restaurant.get('name', 'N/A')}")
        try:
            place_id = restaurant.get('place_id')
            if not place_id:
                logger.warning("Warning: Place is missing place_id, skipping detail retrieval.")
                return None

            language_param = None if use_original_language else 'en'

            # Ensure 'geometry' field is requested to get latitude and longitude
            place_details = self._make_api_call(
                self.gmaps.place,
                place_id=place_id,
                fields=['name', 'rating', 'user_ratings_total', 'formatted_address', 'reviews', 'opening_hours',
                        'geometry'],
                language=language_param
            )
            logger.info(f"API call count (Place Details): {self.api_call_count}")

            if not place_details or 'result' not in place_details:
                logger.warning(f"Could not get results for {place_id} from Place Details API.")
                return None

            result = place_details['result']

            restaurant_info = {
                'place_id': place_id,  # Ensure place_id is included here
                'name': result.get('name', 'N/A'),
                'rating': result.get('rating', 'N/A'),
                'total_ratings': result.get('user_ratings_total', 'N/A'),
                'address': result.get('formatted_address', 'N/A'),
                'reviews': []
            }

            # Extract latitude and longitude information
            if 'geometry' in result and 'location' in result['geometry']:
                restaurant_info['latitude'] = result['geometry']['location'].get('lat')
                restaurant_info['longitude'] = result['geometry']['location'].get('lng')
            else:
                restaurant_info['latitude'] = 'N/A'
                restaurant_info['longitude'] = 'N/A'
                logger.warning(f"Warning: Failed to get latitude/longitude for {restaurant_info['name']}.")

            opening_hours_data = result.get('opening_hours')
            if opening_hours_data and 'weekday_text' in opening_hours_data:
                restaurant_info['opening_hours'] = json.dumps(opening_hours_data['weekday_text'], ensure_ascii=False)
            else:
                restaurant_info['opening_hours'] = 'N/A'

            reviews = result.get('reviews', [])
            for review in reviews:
                review_info = {
                    'author': review.get('author_name', 'N/A'),
                    'rating': review.get('rating', 'N/A'),
                    'text': review.get('text', 'N/A'),
                    'time': datetime.fromtimestamp(review.get('time', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                    'language': review.get('language', 'unknown')
                }
                restaurant_info['reviews'].append(review_info)

            logger.debug(f"Successfully retrieved details for {restaurant_info['name']}.")
            return restaurant_info

        except Exception as e:
            logger.error(f"Error occurred while getting place details: {e}", exc_info=True)
            return None

    def save_to_csv(self, filename='restaurants_data.csv'):
        logger.debug(f"Saving data to {filename}...")
        try:
            # Ensure fieldnames include latitude and longitude
            fieldnames = ['restaurant_name', 'rating', 'total_ratings', 'address', 'latitude', 'longitude', 'place_id',
                          'opening_hours',
                          'review_author', 'review_rating', 'review_text', 'review_time', 'review_language']

            with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for restaurant in self.restaurants_data:
                    restaurant_base = {
                        'restaurant_name': restaurant['name'],
                        'rating': restaurant['rating'],
                        'total_ratings': restaurant['total_ratings'],
                        'address': restaurant['address'],
                        'latitude': restaurant.get('latitude', 'N/A'),  # Get from dictionary
                        'longitude': restaurant.get('longitude', 'N/A'),  # Get from dictionary
                        'place_id': restaurant.get('place_id', ''),
                        'opening_hours': restaurant.get('opening_hours', 'N/A')
                    }

                    if restaurant['reviews']:
                        for review in restaurant['reviews']:
                            writer.writerow({
                                **restaurant_base,
                                'review_author': review['author'],
                                'review_rating': review['rating'],
                                'review_text': review['text'],
                                'review_time': review['time'],
                                'review_language': review.get('language', 'unknown')
                            })
                    else:
                        writer.writerow({
                            **restaurant_base,
                            'review_author': '',
                            'review_rating': '',
                            'review_text': '',
                            'review_time': '',
                            'review_language': ''
                        })

            logger.info(f"Data has been saved to {filename}")
            logger.info(f"A total of {len(self.restaurants_data)} place data entries were fetched")
            logger.info(f"Number of unique places saved: {len(self.processed_place_ids)}")

        except Exception as e:
            logger.error(f"Error while saving CSV: {e}", exc_info=True)

    def print_summary(self):
        print("\n" + "=" * 60)
        print("Grid search complete! Search results summary")
        print("=" * 60)
        print(f"Total places found: {len(self.restaurants_data)} (including duplicate detail entries)")
        print(f"Number of unique places: {len(self.processed_place_ids)}")
        print(f"API call count: {self.api_call_count}")
        print(f"Estimated cost: ${self.api_call_count * 0.017:.2f} USD")

        total_reviews = sum(len(restaurant['reviews']) for restaurant in self.restaurants_data)
        print(f"Total reviews: {total_reviews}")

        if len(self.restaurants_data) > 0:
            avg_reviews_per_restaurant = total_reviews / len(self.restaurants_data)
            print(f"Average reviews per place: {avg_reviews_per_restaurant:.1f}")

        ratings = [r['rating'] for r in self.restaurants_data if isinstance(r['rating'], (int, float))]
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
            print(f"Average rating: {avg_rating:.1f}/5.0")

        print("=" * 60)


def get_location_config():
    return [
        {
            "name": "Birmingham City Centre, Birmingham, UK",
            "radius": 1000,
            "limit": 60,
            "description": "Birmingham city center core area"
        },
        {
            "name": "Birmingham Jewellery Quarter, Birmingham, UK",
            "radius": 800,
            "limit": 60,
            "description": "Jewellery Quarter"
        },
        {
            "name": "Birmingham Chinatown, Birmingham, UK",
            "radius": 600,
            "limit": 60,
            "description": "Chinatown area"
        },
        {
            "name": "Brindleyplace, Birmingham, UK",
            "radius": 800,
            "limit": 60,
            "description": "Brindleyplace"
        },
        {
            "name": "Digbeth, Birmingham, UK",
            "radius": 800,
            "limit": 60,
            "description": "Digbeth area"
        },
        {
            "name": "Birmingham Mailbox, Birmingham, UK",
            "radius": 600,
            "limit": 60,
            "description": "Mailbox shopping center area"
        },
        {
            "name": "Birmingham New Street Station, Birmingham, UK",
            "radius": 500,
            "limit": 60,
            "description": "New Street Station area"
        },
        {
            "name": "Bull Ring, Birmingham, UK",
            "radius": 500,
            "limit": 60,
            "description": "Bull Ring shopping center"
        },

        {
            "name": "University of Birmingham, Birmingham, UK",
            "radius": 2000,
            "limit": 60,
            "description": "University of Birmingham main campus"
        },
        {
            "name": "Selly Oak, Birmingham, UK",
            "radius": 1500,
            "limit": 60,
            "description": "Selly Oak area (student area)"
        },
        {
            "name": "Edgbaston, Birmingham, UK",
            "radius": 1200,
            "limit": 60,
            "description": "Edgbaston area"
        }
    ]