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

# --- Configuration Constants ---
API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
if not API_KEY:
    print("Error: GOOGLE_MAPS_API_KEY environment variable not set. Please set it before running the application.")
    raise ValueError("GOOGLE_MAPS_API_KEY environment variable not set.")

gmaps_client = googlemaps.Client(key=API_KEY)

DEFAULT_MIN_REVIEWS = 10
DEFAULT_MIN_RATING = 3.5

# Bayesian Average Parameters
M_BAYESIAN_AVG_CONFIDENCE = 10
MIN_RATINGS_THRESHOLD = 10

# Sentiment Weight Factor
SENTIMENT_WEIGHT_FACTOR = 0.2


# --- Data Loading ---
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

    for col in ['food_type_tags', 'priority_tags', 'all_keywords_for_recommendation', 'opening_hours']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x:
                                    None if pd.isna(x) or (isinstance(x, str) and x.strip().lower() == 'nan')
                                    else (json.loads(x) if isinstance(x, str) and (
                                                x.startswith('[') or x.startswith('{')) else x)
                                    )

    numeric_cols = ['avg_rating', 'total_ratings', 'avg_sentiment_compound', 'latitude', 'longitude']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    if 'avg_sentiment_compound' in df.columns:
        df['avg_sentiment_compound'] = df['avg_sentiment_compound'].fillna(0)

    print(f"Loaded {len(df)} restaurants from {filename}.")
    return df


RESTAURANT_DATA_FILE = "birmingham_restaurants_20250818_231548_processed.csv"
restaurant_data_df = load_processed_data(RESTAURANT_DATA_FILE)


# --- Utility Functions ---
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


# New unified rating calculation function
def calculate_final_rating(df, keywords=None):
    """
    Calculates the final weighted rating for restaurants based on Bayesian average,
    sentiment score, and keyword bonus.
    Args:
        df (pd.DataFrame): DataFrame with restaurant data.
        keywords (list): List of user-parsed keywords for bonus points.
    Returns:
        pd.DataFrame: DataFrame with the 'final_weighted_rating' column.
    """
    if df.empty:
        return df

    df_temp = df.copy()

    # 1. Calculate Bayesian Average
    C = df_temp['avg_rating'].mean()
    M = M_BAYESIAN_AVG_CONFIDENCE
    df_temp['weighted_rating'] = df_temp.apply(
        lambda x: ((x['total_ratings'] / (x['total_ratings'] + M)) * x['avg_rating']) + \
                  ((M / (x['total_ratings'] + M)) * C), axis=1
    )

    # 2. Add sentiment score bonus
    if 'avg_sentiment_compound' in df_temp.columns:
        df_temp['weighted_rating'] += (SENTIMENT_WEIGHT_FACTOR * df_temp['avg_sentiment_compound'])

    # 3. Add tag bonus based on keywords
    if keywords:
        def tag_bonus(row):
            score = 0.0
            for kw in keywords:
                # Ensure the column exists and is a list
                if isinstance(row.get('all_keywords_for_recommendation'), list):
                    if any(re.search(re.escape(kw), str(tag), re.IGNORECASE) for tag in
                           row['all_keywords_for_recommendation']):
                        score += 0.03
            return min(score, 0.15)

        df_temp['weighted_rating'] += df_temp.apply(tag_bonus, axis=1)

    return df_temp


app = Flask(__name__, template_folder='templates', static_folder='static')


@app.route('/', methods=['GET', 'POST'])
def index():
    recommendations_df = pd.DataFrame()
    user_thought = ''
    user_location_input = ''
    user_radius_input = ''
    error_message = None
    selected_location_source = 'current_location'

    user_lat, user_lng = None, None

    if request.method == 'POST':
        user_thought = request.form.get('user_thought', '')
        user_location_input = request.form.get('user_location_input', '').strip()
        user_radius_input = request.form.get('user_radius_input', '').strip()
        selected_location_source = request.form.get('location_source', 'current_location')

        try:
            user_lat = float(request.form.get('user_lat')) if request.form.get('user_lat') else None
            user_lng = float(request.form.get('user_lng')) if request.form.get('user_lng') else None
        except (ValueError, TypeError):
            print("Invalid coordinates received from form.")
            user_lat, user_lng = None, None

        if selected_location_source == 'manual_input' and user_location_input and (
                user_lat is None or user_lng is None):
            try:
                geocode_result = gmaps_client.geocode(user_location_input)
                if geocode_result:
                    user_lat = geocode_result[0]['geometry']['location']['lat']
                    user_lng = geocode_result[0]['geometry']['location']['lng']
                else:
                    error_message = f"Could not find coordinates for '{user_location_input}'. Please check the spelling."
            except Exception as e:
                error_message = f"Geocoding error: {e}"

        if not restaurant_data_df.empty:
            # 1. Distance filter (pre-filter)
            if user_radius_input:
                try:
                    radius_meters = int(user_radius_input)
                    if radius_meters > 0 and user_lat is not None and user_lng is not None:
                        temp_df = filter_restaurants_by_distance(restaurant_data_df, user_lat, user_lng, radius_meters)
                        if temp_df.empty:
                            error_message = f"No restaurants found within your selected {radius_meters}m radius."
                    elif radius_meters <= 0:
                        error_message = "Search radius must be a positive number."
                        temp_df = pd.DataFrame()
                    else:
                        temp_df = restaurant_data_df.copy()
                except ValueError:
                    error_message = f"Invalid search radius '{user_radius_input}'. Please enter a valid number."
                    temp_df = pd.DataFrame()
            else:
                temp_df = restaurant_data_df.copy()

            if error_message is None:
                parsed_food_types = []
                parsed_priority_keywords = []
                min_rating = DEFAULT_MIN_RATING
                min_reviews = DEFAULT_MIN_REVIEWS

                if user_thought:
                    # Parse rating and reviews from user input
                    rating_match = re.search(r'(?:over\s*)?([\d\.]+) stars?', user_thought, re.IGNORECASE)
                    if rating_match:
                        try:
                            min_rating = float(rating_match.group(1))
                        except ValueError:
                            pass
                    reviews_match = re.search(r'(\d+) reviews?', user_thought, re.IGNORECASE)
                    if reviews_match:
                        try:
                            min_reviews = int(reviews_match.group(1))
                        except ValueError:
                            pass

                    # Parse food and priority keywords
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

                # 2. Filter by minimum rating and reviews (using original avg_rating)
                filtered_df = temp_df[
                    (temp_df['avg_rating'] >= min_rating) &
                    (temp_df['total_ratings'] >= min_reviews)
                    ].copy()

                if filtered_df.empty:
                    error_message = f"No restaurants found with at least {min_rating} stars and {min_reviews} reviews."
                else:
                    # 3. Calculate final weighted rating based on user preferences
                    all_parsed_keywords = parsed_food_types + parsed_priority_keywords
                    recommendations_df = calculate_final_rating(filtered_df, keywords=all_parsed_keywords)

                    # 4. Filter by food/priority tags
                    def match_tags(restaurant_tags, parsed_tags):
                        if not parsed_tags:
                            return True
                        if not isinstance(restaurant_tags, list):
                            return False
                        return any(
                            p_tag.lower() in [r_tag.lower() for r_tag in restaurant_tags] for p_tag in parsed_tags)

                    if parsed_food_types:
                        recommendations_df = recommendations_df[
                            recommendations_df['food_type_tags'].apply(lambda x: match_tags(x, parsed_food_types))
                        ].copy()
                    if parsed_priority_keywords:
                        recommendations_df = recommendations_df[
                            recommendations_df['priority_tags'].apply(lambda x: match_tags(x, parsed_priority_keywords))
                        ].copy()

                    if recommendations_df.empty:
                        error_message = "No restaurants found matching your specific preferences."

                    # 5. Final sort and take top 10
                    if error_message is None:
                        recommendations_df = recommendations_df.sort_values(
                            by=['weighted_rating', 'total_ratings'], ascending=[False, False]
                        ).head(10)

        else:
            error_message = "Restaurant data is not available. Please try again later."

    recommendations_list = []
    if recommendations_df is not None and not recommendations_df.empty:
        if 'distance_m' not in recommendations_df.columns and user_lat is not None and user_lng is not None:
            recommendations_df = filter_restaurants_by_distance(
                recommendations_df, user_lat, user_lng, float('inf')
            )
        elif 'distance_m' not in recommendations_df.columns:
            recommendations_df['distance_m'] = None

        recommendations_list = recommendations_df.replace({np.nan: None}).to_dict('records')

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
        keywords_str = request.args.get('keywords', '')
        keywords = keywords_str.split(',') if keywords_str else None

        if lat is None or lng is None or radius is None:
            return jsonify({"error": "Latitude, longitude, or radius missing."}), 400

        if restaurant_data_df.empty:
            return jsonify({"error": "Restaurant data not loaded. Please try again later."}), 500

        # 1. Distance filter (pre-filter)
        nearby_df = filter_restaurants_by_distance(restaurant_data_df, lat, lng, radius)

        # 2. Minimum ratings threshold filter
        nearby_df = nearby_df[nearby_df['total_ratings'] >= MIN_RATINGS_THRESHOLD].copy()

        if nearby_df.empty:
            avg_data_lat = restaurant_data_df['latitude'].mean()
            avg_data_lng = restaurant_data_df['longitude'].mean()
            if calculate_distance(lat, lng, avg_data_lat, avg_data_lng) > 50000:
                return jsonify(
                    {"error": "Your current location might be outside our Birmingham data coverage area."}), 400
            else:
                return jsonify([]), 200

        # 3. Calculate final rating with bonuses
        nearby_df = calculate_final_rating(nearby_df, keywords=keywords)

        # 4. Final sort and take top 5
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