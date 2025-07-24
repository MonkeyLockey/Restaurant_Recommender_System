from flask import Flask, render_template, request
import pandas as pd
import json
import os
import re
import googlemaps
import math

# --- Google Maps API Key ---
# IMPORTANT: Replace with your actual Google Maps API Key!
GMAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
# ---------------------------

# Initialize Google Maps client
gmaps_client = googlemaps.Client(key=GMAPS_API_KEY)

# --- Configuration for Recommendation Logic ---
# Minimum number of *overall Google ratings* a restaurant must have to be considered for recommendation
MIN_RATINGS_THRESHOLD = 30
# Parameters for Bayesian Average (Weighted Rating)
# C = Overall average rating across ALL restaurants (will be calculated dynamically)
# M_BAYESIAN_AVG_CONFIDENCE: Minimum number of *overall Google ratings* for a restaurant's avg_rating
# to be considered "reliable" for Bayesian Average.
M_BAYESIAN_AVG_CONFIDENCE = 20


# ----------------------------------------------

# --- Core logic copied from recommendation_system.py ---
# Load processed data
def load_processed_data(filename):
    """
    Loads processed restaurant data from a CSV file.
    Args:
        filename (str): Path to the processed CSV file.
    Returns:
        pd.DataFrame: Loaded data.
    """
    if not os.path.exists(filename):
        print(f"Error: File '{filename}' not found. Please check the file path and name.")
        return pd.DataFrame()
    try:
        df = pd.read_csv(filename, encoding='utf-8-sig', engine='python')

        def parse_json_list(s):
            # Returns an empty list if the value is NaN or an empty string
            if pd.isna(s) or s == '':
                return []
            try:
                # Attempt to parse the JSON string
                return json.loads(s)
            except json.JSONDecodeError as e:
                # Print a warning and return an empty list if parsing fails
                print(f"Warning: JSON parsing error '{e}'. Original string: '{s}'. Returning empty list.")
                return []
            except Exception as e:
                # Catch other unknown errors
                print(f"Warning: Unknown error '{e}' parsing string: '{s}'. Returning empty list.")
                return []

        # Convert stored JSON strings back to Python lists
        df['food_type_tags'] = df['food_type_tags'].apply(parse_json_list)
        df['priority_tags'] = df['priority_tags'].apply(parse_json_list)
        df['opening_hours'] = df['opening_hours'].apply(parse_json_list)

        # --- Enhanced type handling for numerical and text columns ---
        # Ensure all numerical columns are float type and fill NaNs
        df['avg_rating'] = pd.to_numeric(df['avg_rating'], errors='coerce').fillna(0.0).astype(float)
        df['avg_sentiment_compound'] = pd.to_numeric(df['avg_sentiment_compound'], errors='coerce').fillna(0.0).astype(
            float)
        df['positive_ratio'] = pd.to_numeric(df['positive_ratio'], errors='coerce').fillna(0.0).astype(float)
        df['negative_ratio'] = pd.to_numeric(df['negative_ratio'], errors='coerce').fillna(0.0).astype(float)

        # Ensure total_ratings is int and fill NaNs
        df['total_ratings'] = pd.to_numeric(df['total_ratings'], errors='coerce').fillna(0).astype(int)
        # total_reviews is the count of scraped reviews, which is max 5. Ensure it's int.
        df['total_reviews'] = pd.to_numeric(df['total_reviews'], errors='coerce').fillna(0).astype(int)

        # Ensure all_review_texts is always a string, fill NaNs
        df['all_review_texts'] = df['all_review_texts'].astype(str).fillna('')

        # Ensure latitude and longitude are float type, fill NaNs
        df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce').fillna(0.0).astype(float)
        df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce').fillna(0.0).astype(float)
        # -----------------------------------------------------------

        print(f"Successfully loaded {len(df)} restaurant data entries for recommendation.")
        return df
    except Exception as e:
        print(f"Error loading processed CSV file: {e}")
        print("Please check file encoding or content format.")
        return pd.DataFrame()


# Haversine distance function
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Radius of Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c  # Distance in meters


# Recommendation algorithm
def recommend_restaurants(restaurant_df, user_preferences, top_n=5, user_lat=None, user_lng=None, search_radius_m=None):
    """
    Recommends restaurants based on user preferences.
    Args:
        restaurant_df (pd.DataFrame): DataFrame containing aggregated restaurant data.
        user_preferences (dict): Dictionary containing user preferences.
        top_n (int): Number of top recommendations to return.
        user_lat (float): Latitude of the user's location.
        user_lng (float): Longitude of the user's location.
        search_radius_m (int): Search radius in meters.
    Returns:
        pd.DataFrame: List of recommended restaurants.
    """
    filtered_df = restaurant_df.copy()

    # --- Initial Filter: Minimum Overall Ratings Threshold ---
    # Only consider restaurants with enough overall Google ratings
    filtered_df = filtered_df[filtered_df['total_ratings'] >= MIN_RATINGS_THRESHOLD].reset_index(drop=True)
    if filtered_df.empty:
        print(
            f"No restaurants found with at least {MIN_RATINGS_THRESHOLD} overall Google ratings after initial filter.")
        return pd.DataFrame()

    # --- 1. Filtering Phase ---
    # Filter by food type
    if user_preferences['food_preference']:
        food_pref_lower = user_preferences['food_preference'].lower()
        filtered_df = filtered_df[
            filtered_df['food_type_tags'].apply(
                lambda tags: any(food_pref_lower in tag.lower() for tag in tags if isinstance(tag, str)))
        ].reset_index(drop=True)

        # Filter by location (text match in address) - This is for the conversational input
    if user_preferences['location']:
        location_lower = user_preferences['location'].lower()
        filtered_df = filtered_df[
            filtered_df['address'].str.contains(location_lower, case=False, na=False)
        ].reset_index(drop=True)

        # Filter by user's precise location and radius
    if user_lat is not None and user_lng is not None and search_radius_m is not None:
        # Calculate distance for each restaurant
        filtered_df['distance_m'] = filtered_df.apply(
            lambda row: haversine_distance(user_lat, user_lng, row['latitude'], row['longitude']),
            axis=1
        )
        # Filter by radius
        filtered_df = filtered_df[filtered_df['distance_m'] <= search_radius_m].reset_index(drop=True)

    # If DataFrame is empty after all filtering, return an empty DataFrame immediately
    if filtered_df.empty:
        return pd.DataFrame()

    # --- 2. Scoring Phase ---
    if not filtered_df.empty:
        filtered_df['recommendation_score'] = 0.0

        # Calculate C (overall average rating) dynamically from the *original* full dataset
        # This ensures C is representative of all available data, not just the filtered subset.
        C_overall_avg_rating = restaurant_df['avg_rating'].mean()
        print(f"Overall average rating (C): {C_overall_avg_rating:.2f}")

        # Calculate Weighted Rating (Bayesian Average) using total_ratings for confidence (v)
        # WR = (R * v + C * m) / (v + m)
        # R = avg_rating, v = total_ratings, C = C_overall_avg_rating, m = M_BAYESIAN_AVG_CONFIDENCE
        filtered_df['weighted_rating'] = filtered_df.apply(
            lambda row: (row['avg_rating'] * row['total_ratings'] + C_overall_avg_rating * M_BAYESIAN_AVG_CONFIDENCE) / \
                        (row['total_ratings'] + M_BAYESIAN_AVG_CONFIDENCE) if (row[
                                                                                   'total_ratings'] + M_BAYESIAN_AVG_CONFIDENCE) > 0 else C_overall_avg_rating,
            axis=1
        )

        # Base score: Use normalized Weighted Rating and normalized Sentiment Score
        filtered_df['normalized_weighted_rating'] = filtered_df['weighted_rating'].astype(
            float) / 5.0  # Normalize WR to 0-1
        filtered_df['normalized_sentiment'] = (filtered_df['avg_sentiment_compound'].astype(float) + 1) / 2.0

        # Adjust weights as needed. Weighted Rating now replaces simple normalized_rating.
        filtered_df['recommendation_score'] += filtered_df[
                                                   'normalized_weighted_rating'] * 0.6  # Give more weight to weighted rating
        filtered_df['recommendation_score'] += filtered_df['normalized_sentiment'] * 0.4

        # Bonus points: mood/atmosphere matching (based on keywords in review text and sentiment)
        if user_preferences['mood']:
            mood_lower = user_preferences['mood'].lower()
            mood_keywords = {
                'quiet': ['quiet', 'peaceful', 'calm', 'relaxing'],
                'lively': ['lively', 'noisy', 'busy', 'energetic', 'vibrant'],
                'romantic': ['romantic', 'intimate', 'date night'],
                'cozy': ['cozy', 'warm', 'comfortable', 'homely']
            }

            if mood_lower in mood_keywords:
                for keyword in mood_keywords[mood_lower]:
                    contains_keyword_int = filtered_df['all_review_texts'].str.contains(keyword, case=False,
                                                                                        na=False).astype(int)
                    positive_ratio_float = filtered_df['positive_ratio'].astype(float)
                    filtered_df['recommendation_score'] += (
                            contains_keyword_int * positive_ratio_float * 0.1
                    )

        # Bonus points: priority matching (based on priority_tags and sentiment)
        if user_preferences['priority']:
            priority_lower = user_preferences['priority'].lower()
            has_priority_tag_int = filtered_df['priority_tags'].apply(
                lambda tags: any(priority_lower in tag.lower() for tag in tags if isinstance(tag, str))).astype(int)
            positive_ratio_float = filtered_df['positive_ratio'].astype(float)
            filtered_df['recommendation_score'] += (
                    has_priority_tag_int * positive_ratio_float * 0.2
            )
    else:
        return pd.DataFrame()

    # --- 3. Sorting and returning Top N ---
    filtered_df['recommendation_score'] = pd.to_numeric(filtered_df['recommendation_score'], errors='coerce').fillna(
        0.0)
    recommended_df = filtered_df.sort_values(by='recommendation_score', ascending=False).head(top_n)

    # Select columns to return, including distance_m, weighted_rating, and place_id
    cols_to_return = [
        'restaurant_name', 'address', 'avg_rating', 'total_ratings',
        'weighted_rating',
        'avg_sentiment_compound',
        'food_type_tags', 'priority_tags', 'recommendation_score', 'opening_hours',
        'place_id'  # 新增: 包含 place_id
    ]
    if 'distance_m' in recommended_df.columns:
        cols_to_return.append('distance_m')

    return recommended_df[cols_to_return]


# --- Function to parse conversational user input ---
def parse_conversational_input(user_thought):
    """
    Parses conversational user input to extract food preference, mood, priority, and location.
    This is a simplified version based on rules and keyword matching.
    Note: This function is currently primarily designed to parse English keywords.
    """
    preferences = {
        'food_preference': None,
        'mood': None,
        'priority': None,
        'location': None
    }
    user_thought_lower = user_thought.lower()

    # Food type keywords (consistent with or extended from data_processor.py's food_keywords)
    food_type_map = {
        'italian': ['italian', 'pasta', 'pizza'],
        'chinese': ['chinese', 'noodles', 'dumplings'],
        'indian': ['indian', 'curry', 'naan'],
        'japanese': ['japanese', 'sushi', 'ramen'],
        'mexican': ['mexican', 'taco', 'burrito'],
        'burger': ['burger', 'fries'],
        'cafe': ['cafe', 'coffee', 'cappuccino'],
        'bar/pub': ['bar', 'pub', 'drinks', 'beer'],
        'fast food': ['fast food', 'takeaway'],
        'vegetarian/vegan': ['vegetarian', 'vegan', 'plant-based'],
        'thai': ['thai', 'pad thai'],
        'mediterranean': ['mediterranean', 'hummus'],
        'dessert': ['dessert', 'sweet', 'cake'],
        'seafood': ['seafood', 'fish', 'prawns'],
        'vietnamese': ['vietnamese', 'pho'],
        'ethiopian': ['ethiopian'],
        'spanish': ['spanish', 'tapas'],
        'breakfast': ['breakfast', 'brunch']
    }

    # Mood/Atmosphere keywords
    mood_map = {
        'quiet': ['quiet', 'peaceful', 'calm', 'relaxing'],
        'lively': ['lively', 'noisy', 'busy', 'energetic', 'vibrant'],
        'romantic': ['romantic', 'intimate', 'date'],
        'cozy': ['cozy', 'warm', 'comfortable', 'homely']
    }

    # Priority keywords
    priority_map = {
        'service': ['service', 'staff', 'friendly', 'attentive'],
        'food quality': ['food quality', 'taste', 'delicious', 'tasty', 'flavour'],
        'atmosphere': ['atmosphere', 'ambiance', 'vibe', 'decor'],
        'value': ['value', 'price', 'cheap', 'expensive', 'affordable'],
        'cleanliness': ['clean', 'dirty', 'hygiene'],
        'waiting time': ['wait', 'queue', 'slow', 'fast'],
        'drinks': ['drinks', 'cocktails', 'wine', 'beer'],
        'location': ['location', 'convenient', 'easy to find'],
        'dietary options': ['vegan', 'vegetarian', 'gluten-free', 'halal', 'allergies']
    }

    # --- Parse food preference ---
    for food_type, keywords in food_type_map.items():
        if any(re.search(r'\b' + keyword + r'\b', user_thought_lower) for keyword in keywords):
            preferences['food_preference'] = food_type
            break

            # --- Parse mood/atmosphere ---
    for mood, keywords in mood_map.items():
        if any(re.search(r'\b' + keyword + r'\b', user_thought_lower) for keyword in keywords):
            preferences['mood'] = mood
            break

    # --- Parse priority ---
    for priority, keywords in priority_map.items():
        if any(re.search(r'\b' + keyword + r'\b', user_thought_lower) for keyword in keywords):
            preferences['priority'] = priority
            break

    # --- Parse location (conversational keyword matching for areas) ---
    birmingham_areas = [
        'birmingham city centre', 'jewellery quarter', 'chinatown',
        'brindleyplace', 'digbeth', 'mailbox', 'new street station',
        'bull ring', 'university of birmingham', 'selly oak', 'edgbaston'
    ]
    for area in birmingham_areas:
        if area in user_thought_lower:
            preferences['location'] = area
            break

    return preferences


app = Flask(__name__)

# --- Configure your processed CSV file path ---
PROCESSED_CSV_FILENAME = "birmingham_restaurants_20250725_000229_processed.csv"
# --------------------------------------------

# Load data once when the application starts
restaurant_data_df = load_processed_data(PROCESSED_CSV_FILENAME)


@app.route('/', methods=['GET', 'POST'])
def index():
    recommendations = None
    user_thought = ""
    error_message = None
    user_location_input = ""
    user_radius_input = ""

    if request.method == 'POST':
        user_thought = request.form.get('user_thought', '').strip()
        user_location_input = request.form.get('user_location_input', '').strip()
        user_radius_input = request.form.get('user_radius_input', '').strip()

        if not user_thought and not user_location_input:
            error_message = "Please enter your thoughts or a location to search!"
        elif restaurant_data_df.empty:
            error_message = "Recommendation data not loaded or is empty. Please check the processed CSV file."
        else:
            # Check if thought input contains non-English characters
            if user_thought and not all(ord(c) < 128 for c in user_thought):
                error_message = "Please enter your conversational preferences in English only."
            else:
                # Parse conversational user input
                user_preferences = parse_conversational_input(user_thought)
                print(f"Parsed conversational preferences: {user_preferences}")

                user_lat, user_lng = None, None
                search_radius_m = None

                # Process user's location and radius input
                if user_location_input:
                    try:
                        geocode_result = gmaps_client.geocode(user_location_input)
                        if geocode_result:
                            user_lat = geocode_result[0]['geometry']['location']['lat']
                            user_lng = geocode_result[0]['geometry']['location']['lng']
                            print(f"Geocoded user location: {user_lat}, {user_lng}")
                        else:
                            error_message = f"Could not find coordinates for '{user_location_input}'. Please check the location spelling."
                    except Exception as e:
                        error_message = f"Error geocoding location: {e}. Please check your Google Maps API Key and network connection."

                if not error_message and user_radius_input:
                    try:
                        search_radius_m = int(user_radius_input)
                        if search_radius_m <= 0:
                            error_message = "Search radius must be a positive number."
                    except ValueError:
                        error_message = "Invalid radius. Please enter a number for the radius."

                if not error_message:
                    # Perform recommendation, passing location and radius
                    # Pass the full restaurant_data_df to recommend_restaurants
                    # so C (overall average rating) can be calculated from the full dataset.
                    recommendations = recommend_restaurants(
                        restaurant_data_df,  # Pass the original full dataframe
                        user_preferences,
                        top_n=5,
                        user_lat=user_lat,
                        user_lng=user_lng,
                        search_radius_m=search_radius_m
                    )

                    if recommendations.empty:
                        # Specific error message for no results within radius
                        if user_lat is not None and user_lng is not None and search_radius_m is not None:
                            error_message = f"Sorry, no restaurants found within {search_radius_m} meters of '{user_location_input}'. Please try broadening your search radius or changing your location."
                        # Check if no restaurants meet the MIN_RATINGS_THRESHOLD
                        elif restaurant_data_df['total_ratings'].max() < MIN_RATINGS_THRESHOLD:
                            error_message = f"No restaurants in your dataset have at least {MIN_RATINGS_THRESHOLD} overall Google ratings. Please lower the minimum ratings threshold in app.py or collect more data."
                        else:
                            error_message = "Sorry, no restaurants matching your preferences were found. Please try broadening your input or changing keywords."

    return render_template('index.html',
                           recommendations=recommendations,
                           user_thought=user_thought,
                           user_location_input=user_location_input,
                           user_radius_input=user_radius_input,
                           error_message=error_message)


if __name__ == '__main__':
    if restaurant_data_df.empty:
        print(
            "Warning: Restaurant data failed to load or is empty. Please ensure the processed CSV file exists and is correctly formatted.")
    app.run(debug=True)
