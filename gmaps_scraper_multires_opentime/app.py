from flask import Flask, render_template, request
import pandas as pd
import json
import os
import re


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

        # Ensure all_review_texts is always a string, fill NaNs
        df['all_review_texts'] = df['all_review_texts'].astype(str).fillna('')
        # -----------------------------------------------------------

        print(f"Successfully loaded {len(df)} restaurant data entries for recommendation.")
        return df
    except Exception as e:
        print(f"Error loading processed CSV file: {e}")
        print("Please check file encoding or content format.")
        return pd.DataFrame()


# Recommendation algorithm
def recommend_restaurants(restaurant_df, user_preferences, top_n=5):
    """
    Recommends restaurants based on user preferences.
    Args:
        restaurant_df (pd.DataFrame): DataFrame containing aggregated restaurant data.
        user_preferences (dict): Dictionary containing user preferences.
        top_n (int): Number of top recommendations to return.
    Returns:
        pd.DataFrame: List of recommended restaurants.
    """
    filtered_df = restaurant_df.copy()

    # --- 1. Filtering Phase ---
    if user_preferences['food_preference']:
        food_pref_lower = user_preferences['food_preference'].lower()
        filtered_df = filtered_df[
            filtered_df['food_type_tags'].apply(
                lambda tags: any(food_pref_lower in tag.lower() for tag in tags if isinstance(tag, str)))
        ].reset_index(drop=True)  # Reset index after filtering to prevent potential issues

    if user_preferences['location']:
        location_lower = user_preferences['location'].lower()
        filtered_df = filtered_df[
            filtered_df['address'].str.contains(location_lower, case=False, na=False)
        ].reset_index(drop=True)  # Reset index after filtering to prevent potential issues

    # If DataFrame is empty after filtering, return an empty DataFrame immediately
    if filtered_df.empty:
        return pd.DataFrame()

    # --- 2. Scoring Phase ---
    # Ensure filtered_df is not empty before proceeding with scoring calculations
    if not filtered_df.empty:
        filtered_df['recommendation_score'] = 0.0

        # Base score: average rating and average sentiment score (with weights)
        # Ensure participating Series are float type
        filtered_df['normalized_rating'] = filtered_df['avg_rating'].astype(float) / 5.0
        filtered_df['normalized_sentiment'] = (filtered_df['avg_sentiment_compound'].astype(float) + 1) / 2.0

        filtered_df['recommendation_score'] += filtered_df['normalized_rating'] * 0.5
        filtered_df['recommendation_score'] += filtered_df['normalized_sentiment'] * 0.5

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
                    # Ensure str.contains returns a boolean Series and convert to int
                    contains_keyword_int = filtered_df['all_review_texts'].str.contains(keyword, case=False,
                                                                                        na=False).astype(int)
                    # Ensure positive_ratio is float
                    positive_ratio_float = filtered_df['positive_ratio'].astype(float)
                    filtered_df['recommendation_score'] += (
                            contains_keyword_int * positive_ratio_float * 0.1
                    )

        # Bonus points: priority matching (based on priority_tags and sentiment)
        if user_preferences['priority']:
            priority_lower = user_preferences['priority'].lower()
            # Ensure apply returns a boolean Series and convert to int
            has_priority_tag_int = filtered_df['priority_tags'].apply(
                lambda tags: any(priority_lower in tag.lower() for tag in tags if isinstance(tag, str))).astype(int)
            # Ensure positive_ratio is float
            positive_ratio_float = filtered_df['positive_ratio'].astype(float)
            filtered_df['recommendation_score'] += (
                    has_priority_tag_int * positive_ratio_float * 0.2
            )
    else:
        # If filtered_df is empty before scoring, return an empty DataFrame
        return pd.DataFrame()

    # --- 3. Sorting and returning Top N ---
    # Ensure recommendation_score exists and is numeric, fill NaNs
    filtered_df['recommendation_score'] = pd.to_numeric(filtered_df['recommendation_score'], errors='coerce').fillna(
        0.0)
    recommended_df = filtered_df.sort_values(by='recommendation_score', ascending=False).head(top_n)

    return recommended_df[[
        'restaurant_name', 'address', 'avg_rating', 'avg_sentiment_compound',
        'food_type_tags', 'priority_tags', 'recommendation_score', 'opening_hours'
    ]]


# --- End of core logic ---


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

    # Check for non-ASCII characters (a simple way to detect non-English text)
    if not all(ord(c) < 128 for c in user_thought):
        return None  # Return None to indicate invalid input language

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

    # --- Parse location (requires more specific location name matching) ---
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
PROCESSED_CSV_FILENAME = "birmingham_restaurants_20250718_012402_processed.csv"
# --------------------------------------------

# Load data once when the application starts
restaurant_data_df = load_processed_data(PROCESSED_CSV_FILENAME)


@app.route('/', methods=['GET', 'POST'])
def index():
    recommendations = None
    user_thought = ""
    error_message = None

    if request.method == 'POST':
        user_thought = request.form.get('user_thought', '').strip()
        if not user_thought:
            error_message = "Please enter your thoughts!"
        elif restaurant_data_df.empty:
            error_message = "Recommendation data not loaded or is empty. Please check the processed CSV file."
        else:
            # Check if input contains non-English characters
            if not all(ord(c) < 128 for c in user_thought):
                error_message = "Please enter your preferences in English only."
            else:
                # Parse conversational user input
                user_preferences = parse_conversational_input(user_thought)
                print(f"Parsed user preferences: {user_preferences}")  # Print to console for debugging

                # Perform recommendation
                recommendations = recommend_restaurants(restaurant_data_df, user_preferences, top_n=5)

                if recommendations.empty:
                    error_message = "Sorry, no restaurants matching your preferences were found. Please try broadening your input or changing keywords."

    return render_template('index.html',
                           recommendations=recommendations,
                           user_thought=user_thought,
                           error_message=error_message)


if __name__ == '__main__':
    if restaurant_data_df.empty:
        print(
            "Warning: Restaurant data failed to load or is empty. Please ensure the processed CSV file exists and is correctly formatted.")
    app.run(debug=True)
