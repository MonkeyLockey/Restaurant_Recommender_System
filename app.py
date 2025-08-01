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
# ---------------------------\

# Initialize Google Maps client
gmaps_client = googlemaps.Client(key=GMAPS_API_KEY)

# --- Configuration for Recommendation Logic ---
# 如果使用者沒有在文字中指定，則使用這些預設值
DEFAULT_MIN_REVIEWS = 10
DEFAULT_MIN_RATING = 3.5

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
        print(f"Error: Processed data file not found at {filename}. Please run data_processor.py first.")
        return pd.DataFrame()

    df = pd.read_csv(filename)

    # Check if necessary columns exist and handle missing columns
    for col in ['food_type_tags', 'priority_tags', 'opening_hours', 'avg_rating', 'total_ratings']:
        if col not in df.columns:
            print(f"Warning: Column '{col}' not found in the CSV. Adding an empty column.")
            df[col] = '[]' if col in ['food_type_tags', 'priority_tags'] else 'N/A'

    # --- FIX: Deserialize JSON strings back to Python lists ---
    # The data_processor.py serializes these as strings, so we need to parse them back.
    def parse_json_column(json_string):
        try:
            return json.loads(json_string) if isinstance(json_string, str) else []
        except (json.JSONDecodeError, TypeError):
            return []

    df['food_type_tags'] = df['food_type_tags'].apply(parse_json_column)
    df['priority_tags'] = df['priority_tags'].apply(parse_json_column)

    # Handle opening_hours, which might be a list of strings or a single string
    df['opening_hours'] = df['opening_hours'].apply(
        lambda x: json.loads(x) if isinstance(x, str) and x.startswith('[') else [x] if isinstance(x,
                                                                                                   str) and x != 'N/A' else []
    )

    print(f"Loaded {len(df)} restaurants from {filename}.")
    print("\nLoaded data preview:")
    print(df[['restaurant_name', 'food_type_tags', 'priority_tags', 'avg_rating']].head())

    return df


# Initialize the Flask app
app = Flask(__name__)
restaurant_data_df = load_processed_data("birmingham_restaurants_20250725_000229_processed.csv")

# Calculate global mean rating C for Bayesian average, if data is available
C = restaurant_data_df['avg_rating'].mean() if not restaurant_data_df.empty else 0.0


# Function to calculate the weighted rating based on the Bayesian average formula
def weighted_rating(row, m=M_BAYESIAN_AVG_CONFIDENCE, c=C):
    v = row['total_ratings']
    R = row['avg_rating']
    # Formula: (v / (v + m) * R) + (m / (v + m) * C)
    return (v / (v + m) * R) + (m / (v + m) * c)


# Function to get coordinates from a location string
def geocode_location(location_name):
    try:
        geocode_result = gmaps_client.geocode(location_name)
        if geocode_result:
            lat = geocode_result[0]['geometry']['location']['lat']
            lng = geocode_result[0]['geometry']['location']['lon']
            return lat, lng
        return None, None
    except Exception as e:
        print(f"Error during geocoding: {e}")
        return None, None


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # radius of Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c  # in meters
    return distance


def parse_user_filters(user_thought):
    """
    從使用者輸入的文字中解析出最低評分和最低評論數，並回傳一個清理後的字串。
    """
    text_lower = user_thought.lower()
    min_rating = DEFAULT_MIN_RATING
    min_reviews = DEFAULT_MIN_REVIEWS

    # 尋找並移除 "over X stars" 或 "rating Y"
    rating_patterns = r'(over\s*(\d\.?\d*)\s*stars?)|(rating\s*(\d\.?\d*))'
    rating_match = re.search(rating_patterns, text_lower)
    if rating_match:
        # 獲取第一個匹配到的群組
        rating_value = rating_match.group(2) or rating_match.group(4)
        try:
            min_rating = float(rating_value)
        except (ValueError, TypeError):
            pass  # 如果轉換失敗，使用預設值
        text_lower = re.sub(rating_patterns, '', text_lower).strip()

    # 尋找並移除 "over X reviews" 或 "at least Y reviews"
    reviews_patterns = r'(over\s*(\d+)\s*reviews?)|(at\s*least\s*(\d+)\s*reviews?)'
    reviews_match = re.search(reviews_patterns, text_lower)
    if reviews_match:
        reviews_value = reviews_match.group(2) or reviews_match.group(4)
        try:
            min_reviews = int(reviews_value)
        except (ValueError, TypeError):
            pass
        text_lower = re.sub(reviews_patterns, '', text_lower).strip()

    print(f"Parsed filters: min_rating={min_rating}, min_reviews={min_reviews}")
    print(f"Cleaned user thought: '{text_lower}'")
    return min_rating, min_reviews, text_lower


def get_recommendations_with_keywords(user_thought_cleaned, min_rating, min_reviews, user_lat=None, user_lng=None,
                                      radius=None):
    if restaurant_data_df.empty:
        return pd.DataFrame(), "餐廳資料載入失敗，請檢查資料檔案。"

    recommendations_df = restaurant_data_df.copy()
    # Initialize a base score and a column for matched keywords
    recommendations_df['score'] = recommendations_df.apply(weighted_rating, axis=1)
    recommendations_df['matched_keywords'] = [[] for _ in range(len(recommendations_df))]

    # 檢查並過濾掉評分不足的餐廳 (使用使用者輸入的值)
    recommendations_df = recommendations_df[
        (recommendations_df['total_ratings'] >= min_reviews) &
        (recommendations_df['avg_rating'] >= min_rating)
        ].copy()

    if user_lat and user_lng:
        recommendations_df['distance_m'] = recommendations_df.apply(
            lambda row: calculate_distance(user_lat, user_lng, row['latitude'], row['longitude']), axis=1)

        if radius:
            recommendations_df = recommendations_df[recommendations_df['distance_m'] <= radius].copy()

    # Process user thought for keywords, using the cleaned string
    if user_thought_cleaned:
        # Use regex to find single words and simple phrases
        user_keywords = re.findall(r'\b\w+\b', user_thought_cleaned.lower())

        # Scoring based on a new tiered priority system: Food > Reviews > Priority Tags
        for index, row in recommendations_df.iterrows():
            score_boost = 0
            matched = []

            # 1. 優先匹配 food_type_tags (最高加權)
            for keyword in user_keywords:
                if keyword in [tag.lower() for tag in row['food_type_tags']]:
                    score_boost += 2.5  # 匹配食物標籤給予最高分數
                    if keyword not in matched:
                        matched.append(keyword)

            # 2. 其次匹配 all_review_texts (中等加權)
            if isinstance(row['all_review_texts'], str):
                review_text_lower = row['all_review_texts'].lower()
                for keyword in user_keywords:
                    if keyword in review_text_lower:
                        score_boost += 1.5  # 匹配評論文字給予中等分數
                        if keyword not in matched:
                            matched.append(keyword)

            # 3. 最後匹配 priority_tags (最低加權)
            for keyword in user_keywords:
                if keyword in [tag.lower() for tag in row['priority_tags']]:
                    score_boost += 0.5  # 匹配重點標籤給予最低分數
                    if keyword not in matched:
                        matched.append(keyword)

            # 應用分數加權並更新匹配關鍵字
            recommendations_df.at[index, 'score'] += score_boost
            recommendations_df.at[index, 'matched_keywords'] = matched

    # Sort by score and return top recommendations
    return recommendations_df.sort_values(by='score', ascending=False).head(10)


# Main route
@app.route('/', methods=['GET', 'POST'])
def index():
    recommendations_df = pd.DataFrame()
    user_thought = ""
    user_location_input = ""
    user_radius_input = ""
    error_message = None

    if request.method == 'POST':
        user_thought = request.form.get('user_thought', '')
        user_location_input = request.form.get('user_location_input', '')
        user_radius_input = request.form.get('user_radius_input', '')

        # 解析使用者輸入文字，獲得動態篩選條件和清理後的關鍵字
        min_rating, min_reviews, cleaned_user_thought = parse_user_filters(user_thought)

        if not restaurant_data_df.empty:
            user_lat, user_lng = None, None
            radius = None

            if user_location_input:
                user_lat, user_lng = geocode_location(user_location_input)

            if user_radius_input:
                try:
                    radius = int(user_radius_input)
                except (ValueError, TypeError):
                    error_message = "Search radius must be a valid number."

            # Proceed with recommendation if no errors
            if not error_message:
                recommendations_df = get_recommendations_with_keywords(
                    cleaned_user_thought, min_rating, min_reviews, user_lat, user_lng, radius
                )

            # Check if recommendations were found
            if recommendations_df.empty:
                # Check for possible reasons
                if user_location_input and (user_lat is None or user_lng is None):
                    error_message = f"Could not find coordinates for '{user_location_input}'. Please check the spelling or try broadening your search radius or changing your location."
                else:
                    error_message = "Sorry, no restaurants matching your preferences were found. Please try broadening your input or changing keywords."

    # --- FIX: Convert DataFrame to a list of dictionaries for JSON serialization ---
    recommendations_list = []
    if recommendations_df is not None:
        recommendations_list = recommendations_df.to_dict('records')

    return render_template('index_with_nearby.html',
                           recommendations=recommendations_list,  # <- 使用轉換後的列表
                           user_thought=user_thought,
                           user_location_input=user_location_input,
                           user_radius_input=user_radius_input,
                           error_message=error_message)


if __name__ == '__main__':
    if restaurant_data_df.empty:
        print(
            "Warning: Restaurant data failed to load or is empty. Please ensure the processed CSV file exists and is correctly formatted.")
    app.run(debug=True)
