from flask import Flask, render_template, request, jsonify
import pandas as pd
import json
import os
import re
import googlemaps
import math
from dotenv import load_dotenv
import traceback
import numpy as np

load_dotenv()

API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
if not API_KEY:
    print("Error: GOOGLE_MAPS_API_KEY environment variable not set. Please set it before running the application.")
    raise ValueError("GOOGLE_MAPS_API_KEY environment variable not set.")

gmaps_client = googlemaps.Client(key=API_KEY)

DEFAULT_MIN_REVIEWS = 10
DEFAULT_MIN_RATING = 3.5

M_BAYESIAN_AVG_CONFIDENCE = 10
MIN_RATINGS_THRESHOLD = 10


def load_processed_data(filename):
    """
    Loads processed restaurant data from a CSV file.
    Args:
        filename (str): Path to the processed CSV file.
    Returns:
        pd.DataFrame: Loaded data.
    """
    if not os.path.exists(filename):
        print(f"Error: Processed data file not found at: {filename}")
        return pd.DataFrame()

    df = pd.read_csv(filename)

    for col in ['food_type_tags', 'priority_tags', 'opening_hours']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x:
                None if pd.isna(x) or (isinstance(x, str) and x.strip().lower() == 'nan')
                else (json.loads(x) if isinstance(x, str) and (x.startswith('[') or x.startswith('{')) else x)
            )

    numeric_cols = ['avg_rating', 'total_ratings', 'avg_sentiment_compound', 'latitude', 'longitude']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    print(f"Loaded {len(df)} restaurants from {filename}.")
    return df


RESTAURANT_DATA_FILE = "birmingham_restaurants_20250818_231548_processed.csv"
restaurant_data_df = load_processed_data(RESTAURANT_DATA_FILE)


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return distance


def filter_restaurants_by_distance(df, user_lat, user_lng, radius_meters):
    if df.empty or user_lat is None or user_lng is None:
        return df.copy()

    df_temp = df.copy()
    df_temp['latitude'] = pd.to_numeric(df_temp['latitude'], errors='coerce')
    df_temp['longitude'] = pd.to_numeric(df_temp['longitude'], errors='coerce')

    df_filtered_coords = df_temp.dropna(subset=['latitude', 'longitude'])

    df_filtered_coords['distance_m'] = df_filtered_coords.apply(
        lambda row: calculate_distance(user_lat, user_lng, row['latitude'], row['longitude']), axis=1
    )

    df_in_radius = df_filtered_coords[df_filtered_coords['distance_m'] <= radius_meters]
    print(f"Filtered {len(df_in_radius)} restaurants within {radius_meters}m radius.")
    return df_in_radius


app = Flask(__name__, template_folder='templates', static_folder='static')


@app.route('/', methods=['GET', 'POST'])
def index():
    recommendations_df = pd.DataFrame()
    user_thought = ''
    user_location_input = ''
    user_radius_input = ''
    error_message = None
    selected_location_source = 'current_location'

    user_lat_from_form = None
    user_lng_from_form = None

    if request.method == 'POST':
        user_thought = request.form.get('user_thought', '')
        user_location_input = request.form.get('user_location_input', '').strip()
        user_radius_input = request.form.get('user_radius_input', '').strip()
        selected_location_source = request.form.get('location_source', 'current_location')

        try:
            user_lat_from_form = float(request.form.get('user_lat')) if request.form.get('user_lat') else None
            user_lng_from_form = float(request.form.get('user_lng')) if request.form.get('user_lng') else None
            print(f"Received coordinates from form: Lat={user_lat_from_form}, Lng={user_lng_from_form}")
        except ValueError:
            user_lat_from_form = None
            user_lng_from_form = None
            print("Invalid coordinates received from form.")

        user_lat, user_lng = user_lat_from_form, user_lng_from_form

        if selected_location_source == 'manual_input' and user_location_input and (
                user_lat is None or user_lng is None):
            try:
                geocode_result = gmaps_client.geocode(user_location_input)
                if geocode_result:
                    user_lat = geocode_result[0]['geometry']['location']['lat']
                    user_lng = geocode_result[0]['geometry']['location']['lng']
                    print(f"Server-side geocoded '{user_location_input}' to Lat: {user_lat}, Lng={user_lng}")
                else:
                    error_message = f"Could not find coordinates for '{user_location_input}'. Please check the spelling."
            except Exception as e:
                error_message = f"Geocoding error: {e}"
                print(f"Geocoding error: {e}")
        elif selected_location_source == 'current_location' and (user_lat is None or user_lng is None):
            error_message = "Please allow browser to fetch your location, or enter a location manually to get recommendations."

        if user_lat is not None and user_lng is not None and not restaurant_data_df.empty:
            temp_df = restaurant_data_df.copy()

            C = temp_df['avg_rating'].mean()
            M = M_BAYESIAN_AVG_CONFIDENCE
            temp_df['weighted_rating'] = temp_df.apply(
                lambda x: ((x['total_ratings'] / (x['total_ratings'] + M)) * x['avg_rating']) + \
                          ((M / (x['total_ratings'] + M)) * C), axis=1
            )

            filtered_df = temp_df[temp_df['total_ratings'] >= MIN_RATINGS_THRESHOLD].copy()

            if user_radius_input:
                try:
                    radius_meters = int(user_radius_input)
                    if radius_meters > 0:
                        print(f"Applying distance filter to main recommendations: {radius_meters}m.")
                        filtered_df = filter_restaurants_by_distance(
                            filtered_df, user_lat, user_lng, radius_meters
                        )
                        if filtered_df.empty:
                            error_message = f"No restaurants found within your selected {radius_meters}m radius. Please try widening the radius or changing search preferences."
                    else:
                        error_message = "Search radius must be a positive number."
                        filtered_df = pd.DataFrame()
                except ValueError:
                    error_message = f"Invalid search radius '{user_radius_input}'. Please enter a valid number."
                    filtered_df = pd.DataFrame()

            if filtered_df.empty and not error_message:
                error_message = "Sorry, no restaurants found matching your specified criteria. Please try broadening your preferences."
                recommendations_df = pd.DataFrame()

            if not error_message and not filtered_df.empty:
                parsed_food_types = []
                parsed_priority_keywords = []
                min_rating = DEFAULT_MIN_RATING
                min_reviews = DEFAULT_MIN_REVIEWS

                if user_thought:
                    rating_match = re.search(r'(?:over\s*)?([\d\.]+) stars?', user_thought, re.IGNORECASE)
                    if rating_match:
                        try:
                            min_rating = float(rating_match.group(1))
                            print(f"Parsed minimum rating from user input: {min_rating}")
                        except ValueError:
                            pass

                    reviews_match = re.search(r'(\d+) reviews?', user_thought, re.IGNORECASE)
                    if reviews_match:
                        try:
                            min_reviews = int(reviews_match.group(1))
                            print(f"Parsed minimum reviews from user input: {min_reviews}")
                        except ValueError:
                            pass

                    all_food_keywords = ["italian", "chinese", "korean", "indian", "japanese", "thai", "mexican",
                                         "vietnamese", "french", "american", "british", "turkish", "greek", "spanish",
                                         "vegetarian", "vegan", "halal", "pizza", "burger", "sushi", "curry", "noodles",
                                         "tapas"]
                    all_priority_keywords = ["relaxing", "cozy", "romantic", "lively", "cheap", "expensive",
                                             "family friendly", "dog friendly", "quick bite", "fine dining",
                                             "street food", "takeaway", "delivery", "brunch", "breakfast", "lunch",
                                             "dinner", "outdoor seating", "good for groups", "date night"]

                    user_thought_lower = user_thought.lower()
                    parsed_food_types = [ft for ft in all_food_keywords if ft in user_thought_lower]
                    parsed_priority_keywords = [pk for pk in all_priority_keywords if pk in user_thought_lower]

                    print(f"Parsed food types from user input: {parsed_food_types}")
                    print(f"Parsed priority keywords from user input: {parsed_priority_keywords}")

                def match_tags(restaurant_tags, parsed_tags):
                    if not parsed_tags:
                        return True
                    if not isinstance(restaurant_tags, list):
                        return False
                    return any(p_tag.lower() in [r_tag.lower() for r_tag in restaurant_tags] for p_tag in parsed_tags)

                if parsed_food_types:
                    filtered_df = filtered_df[
                        filtered_df['food_type_tags'].apply(lambda x: match_tags(x, parsed_food_types))
                    ].copy()

                if parsed_priority_keywords:
                    filtered_df = filtered_df[
                        filtered_df['priority_tags'].apply(lambda x: match_tags(x, parsed_priority_keywords))
                    ].copy()

                if min_rating != DEFAULT_MIN_RATING:
                    final_rating_filter = (filtered_df['avg_rating'] >= min_rating)
                    print(f"Filtering by actual average rating >= {min_rating} due to explicit user request.")
                else:
                    final_rating_filter = (filtered_df['weighted_rating'] >= min_rating)
                    print(f"Filtering by weighted rating >= {min_rating} as no explicit rating was requested.")

                recommendations_df = filtered_df[
                    final_rating_filter &
                    (filtered_df['total_ratings'] >= min_reviews)
                ].copy()

                recommendations_df = recommendations_df.sort_values(
                    by=['weighted_rating', 'total_ratings'], ascending=[False, False]
                ).head(10)

        elif user_lat is None or user_lng is None:
            pass

    recommendations_list = []
    if recommendations_df is not None and not recommendations_df.empty:
        if 'distance_m' not in recommendations_df.columns and user_lat is not None and user_lng is not None:
            recommendations_df = filter_restaurants_by_distance(
                recommendations_df, user_lat, user_lng, float('inf')
            )
        elif 'distance_m' not in recommendations_df.columns:
            recommendations_df['distance_m'] = None

        recommendations_list = recommendations_df.to_dict('records')

    return render_template('home.html',
                           recommendations=recommendations_list,
                           user_thought=user_thought,
                           user_location_input=user_location_input,
                           user_radius_input=user_radius_input,
                           error_message=error_message,
                           selected_location_source=selected_location_source,
                           gmaps_api_key=API_KEY)


@app.route('/get_nearby_restaurants')
def get_nearby_restaurants():
    """
    API endpoint for frontend AJAX calls to fetch top-rated nearby restaurants.
    """
    try:
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)
        radius = request.args.get('radius', type=int)

        if lat is None or lng is None or radius is None:
            return jsonify({"error": "Latitude, longitude, or radius missing."}), 400

        if restaurant_data_df.empty:
            return jsonify({"error": "Restaurant data not loaded. Please try again later."}), 500

        C = restaurant_data_df['avg_rating'].mean()
        M = M_BAYESIAN_AVG_CONFIDENCE

        temp_df = restaurant_data_df.copy()
        temp_df['weighted_rating'] = temp_df.apply(
            lambda x: ((x['total_ratings'] / (x['total_ratings'] + M)) * x['avg_rating']) + \
                      ((M / (x['total_ratings'] + M)) * C), axis=1
        )

        nearby_df = filter_restaurants_by_distance(temp_df, lat, lng, radius)

        nearby_df = nearby_df[nearby_df['total_ratings'] >= MIN_RATINGS_THRESHOLD].copy()

        if nearby_df.empty:
            avg_data_lat = restaurant_data_df['latitude'].mean()
            avg_data_lng = restaurant_data_df['longitude'].mean()
            if calculate_distance(lat, lng, avg_data_lat, avg_data_lng) > 50000:
                return jsonify(
                    {"error": "Your current location might be outside our Birmingham data coverage area. Please try a location closer to Birmingham city center."}), 400
            else:
                return jsonify([]), 200

        top_nearby_df = nearby_df.sort_values(
            by=['weighted_rating', 'total_ratings'], ascending=[False, False]
        ).head(5)

        top_nearby_list = top_nearby_df.replace({np.nan: None}).to_dict('records')
        return jsonify(top_nearby_list)

    except Exception as e:
        print(f"An unexpected error occurred in /get_nearby_restaurants: {e}")
        traceback.print_exc()
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}. Please try again later."}), 500


if __name__ == '__main__':
    if restaurant_data_df.empty:
        print(
            "Warning: Restaurant data failed to load or is empty. Please ensure the processed CSV file exists and is correctly formatted.")
    app.run(debug=True)