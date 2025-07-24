import pandas as pd
import json
import re
from collections import Counter
import os


def get_restaurant_tags(all_review_texts):
    """
    Generates food type and priority tags for a restaurant based on merged review texts.
    Args:
        all_review_texts (str): Merged text of all reviews for the restaurant.
    Returns:
        tuple: (food_type_tag_list, priority_tags_list)
    """
    food_type_tags = []
    priority_tags = []

    # Convert text to lowercase for matching
    text_lower = all_review_texts.lower()

    # --- Food Type Tags (Expanded) ---
    food_keywords = {
        'Italian': ['pasta', 'pizza', 'italian food', 'risotto', 'lasagna', 'tiramisu', 'gelato', 'calzone',
                    'antipasto'],
        'Chinese': ['noodles', 'dumplings', 'fried rice', 'sichuan', 'cantonese', 'chinese food', 'dim sum', 'wonton',
                    'chow mein', 'sweet and sour', 'spring rolls', 'dezhou chicken', 'biangbiang noodles',
                    'braised chicken', 'hand pulled noodles'],
        'Indian': ['curry', 'naan', 'tikka', 'masala', 'indian food', 'bhaji', 'samosa', 'biryani', 'rogan josh',
                   'tandoori', 'dosa', 'puri', 'south indian food'],
        'Japanese': ['sushi', 'ramen', 'sashimi', 'tempura', 'japanese food', 'udon', 'teriyaki', 'miso', 'nigiri',
                     'sake', 'chicken noodle'],
        'Mexican': ['taco', 'burrito', 'nachos', 'mexican food', 'quesadilla', 'guacamole', 'salsa', 'enchilada',
                    'fajita'],
        'Burger': ['burger', 'fries', 'cheeseburger', 'patty', 'bun', 'sliders'],
        'Cafe': ['coffee', 'latte', 'cappuccino', 'bakery', 'cake', 'cafe', 'espresso', 'pastry', 'sandwich', 'brunch',
                 'breakfast', 'frappe', 'bagel', 'chai'],
        'Bar/Pub': ['beer', 'cocktail', 'pub', 'drinks', 'bar', 'ale', 'lager', 'wine', 'spirits', 'pint', 'happy hour',
                    'gin', 'club', 'night out'],
        'Fast Food': ['fast food', 'takeaway', 'quick bite', 'drive-thru', 'delivery', 'fried chicken', 'chips', 'subs',
                      'sandwich'],
        'Vegetarian/Vegan': ['vegetarian', 'vegan', 'plant-based', 'meat-free', 'veggie', 'quorn'],
        'Thai': ['thai food', 'pad thai', 'green curry', 'red curry', 'tom yum', 'thai tofu'],
        'Mediterranean': ['mediterranean', 'hummus', 'falafel', 'kebab', 'pita', 'greek food', 'turkish food'],
        'Dessert': ['dessert', 'ice cream', 'chocolate', 'pudding', 'sweet', 'lemon posset', 'tiramisu'],
        'Seafood': ['seafood', 'fish', 'prawns', 'lobster', 'oysters', 'mussels', 'crab', 'salmon'],
        'Vietnamese': ['vietnamese', 'pho', 'bun-cha-ha-noi', 'duck dumplings', 'spring roll', 'lemongrass chicken'],
        'Ethiopian': ['ethiopian food', 'wot', 'tej', 'blue nile specialty', 'tilapia fish', 'platter'],
        'Spanish': ['spanish food', 'tapas', 'paella', 'meatballs', 'cannelloni', 'semifredo'],
        'Indian Street Food': ['dosa', 'puri', 'samosa', 'bhaji', 'chaat'],
        'Breakfast': ['breakfast', 'full english', 'omelette', 'bacon bap']
    }

    for food_type, keywords in food_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            food_type_tags.append(food_type)

    if not food_type_tags:
        food_type_tags.append('General Cuisine')

    # --- Priority/Aspect Tags (Expanded) ---
    aspect_keywords = {
        'Service': ['service', 'staff', 'waiter', 'waitress', 'friendly', 'rude', 'slow', 'attentive', 'polite',
                    'helpful', 'unresponsive', 'customer service', 'courtesy', 'served', 'team'],
        'Food Quality': ['food', 'taste', 'delicious', 'tasty', 'flavour', 'quality', 'cold', 'bland', 'fresh', 'hot',
                         'portion', 'menu', 'dishes', 'ingredients', 'overcooked', 'undercooked', 'authentic', 'dry',
                         'hard', 'flavourful', 'succulent', 'inedible', 'crispiness', 'filling', 'seasoning'],
        'Atmosphere': ['atmosphere', 'ambiance', 'cozy', 'loud', 'noisy', 'decor', 'vibe', 'lighting', 'music',
                       'comfortable', 'crowded', 'spacious', 'romantic', 'chilled', 'traditional', 'modern', 'private',
                       'community'],
        'Value': ['price', 'expensive', 'cheap', 'value for money', 'affordable', 'cost', 'bill', 'overpriced',
                  'bargain'],
        'Cleanliness': ['clean', 'dirty', 'hygiene', 'toilet', 'restroom', 'table', 'utensils'],
        'Location': ['location', 'convenient', 'easy to find', 'parking', 'accessible', 'central', 'hidden',
                     'proximity', 'situated'],
        'Waiting Time': ['wait', 'waiting', 'queue', 'slow service', 'fast service', 'quick service', 'rapid service'],
        'Drinks': ['drinks', 'cocktails', 'wine list', 'beer selection', 'coffee', 'tea', 'mocktails', 'ale', 'lager',
                   'frappe', 'flat white'],
        'Experience': ['experience', 'enjoyed', 'disappointed', 'loved', 'hated', 'overall', 'memorable', 'fun',
                       'uncomfortable', 'dreadful'],
        'Portion Size': ['portion', 'size', 'generous', 'small', 'big', 'filling'],
        'Dietary Options': ['vegan options', 'vegetarian options', 'gluten-free', 'allergies', 'halal', 'non halal'],
        'Seating/Comfort': ['uncomfortable', 'chairs', 'booth', 'sitting area', 'garden'],
        'Booking/Entry': ['booked', 'entry', 'bouncers', 'queue', 'discrimination'],
        'Communication/Responsiveness': ['email', 'response', 'unresponsive', 'complaint'],
        'Sound/Noise': ['music', 'loud', 'noisy', 'acoustics'],
        'Ventilation/AC': ['air conditioning', 'air circulation', 'hot', 'fan', 'ventilation']
    }

    for aspect, keywords in aspect_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            priority_tags.append(aspect)

    return food_type_tags, priority_tags


def process_and_tag_data(sentiment_csv_filename):
    """
    Loads sentiment-analyzed CSV, aggregates data, and tags restaurants.
    Args:
        sentiment_csv_filename (str): Path to the sentiment-analyzed CSV file.
    Returns:
        pd.DataFrame: Processed and tagged restaurant data.
    """
    print(f"\n--- Starting data processing and tagging for restaurants ---")
    print(f"Loading sentiment analysis results file: '{sentiment_csv_filename}'")

    if not os.path.exists(sentiment_csv_filename):
        print(f"Error: File '{sentiment_csv_filename}' not found. Please check the file path and name.")
        return pd.DataFrame()

    try:
        df_sentiment = pd.read_csv(sentiment_csv_filename, encoding='utf-8-sig', engine='python')
        print(f"Successfully loaded {len(df_sentiment)} review entries.")
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        print("Please check file encoding or content format.")
        return pd.DataFrame()

    # Ensure 'review_text' column is string type and handle missing values
    if 'review_text' in df_sentiment.columns:
        df_sentiment['review_text'] = df_sentiment['review_text'].astype(str).fillna('')
    else:
        print("Warning: CSV file does not contain 'review_text' column. Review text analysis not possible.")
        return pd.DataFrame()

    # --- Aggregate data for each restaurant ---
    print("\nAggregating review data for each restaurant...")
    aggregated_df = df_sentiment.groupby('place_id').agg(
        restaurant_name=('restaurant_name', 'first'),
        address=('address', 'first'),
        avg_rating=('rating', 'first'),
        total_ratings=('total_ratings', 'first'),  # 新增: 聚合總評分數量
        avg_sentiment_compound=('sentiment_compound', 'mean'),
        total_reviews=('review_text', 'count'),  # 這是抓取到的評論數量 (最多5條)
        positive_review_count=('sentiment_label', lambda x: (x == 'Positive').sum()),
        negative_review_count=('sentiment_label', lambda x: (x == 'Negative').sum()),
        neutral_review_count=('sentiment_label', lambda x: (x == 'Neutral').sum()),
        latitude=('latitude', 'first'),
        longitude=('longitude', 'first'),
        opening_hours=('opening_hours', 'first'),
        all_review_texts=('review_text', lambda x: " ".join(x.dropna().tolist()))
    ).reset_index()

    aggregated_df['positive_ratio'] = aggregated_df['positive_review_count'] / aggregated_df['total_reviews']
    aggregated_df['negative_ratio'] = aggregated_df['negative_review_count'] / aggregated_df['total_reviews']
    aggregated_df[['positive_ratio', 'negative_ratio']] = aggregated_df[['positive_ratio', 'negative_ratio']].fillna(0)

    print(f"Aggregated data for {len(aggregated_df)} unique places.")
    print("\nAggregated data preview:")
    print(aggregated_df.head())

    # --- Apply keyword tagger ---
    print("\nTagging restaurants (food types and priorities)...")
    tags_result = aggregated_df['all_review_texts'].apply(get_restaurant_tags)
    aggregated_df['food_type_tags'] = tags_result.apply(lambda x: x[0])
    aggregated_df['priority_tags'] = tags_result.apply(lambda x: x[1])

    # --- Serialize tags to JSON strings before saving ---
    aggregated_df['food_type_tags'] = aggregated_df['food_type_tags'].apply(json.dumps)
    aggregated_df['priority_tags'] = aggregated_df['priority_tags'].apply(json.dumps)
    aggregated_df['opening_hours'] = aggregated_df['opening_hours'].apply(
        lambda x: x if isinstance(x, str) else json.dumps(x) if isinstance(x, list) else 'N/A')

    print("Tagging complete!")
    print("\nTagged data preview:")
    print(aggregated_df[['restaurant_name', 'food_type_tags', 'priority_tags', 'avg_rating', 'total_ratings',
                         'avg_sentiment_compound']].head())  # 顯示 total_ratings

    # --- Save processed data ---
    output_processed_csv = sentiment_csv_filename.replace("_sentiment.csv", "_processed.csv")
    aggregated_df.to_csv(output_processed_csv, index=False, encoding='utf-8-sig')
    print(f"\nProcessed restaurant data saved to: {output_processed_csv}")

    return aggregated_df


if __name__ == "__main__":
    sentiment_csv_to_process = "birmingham_restaurants_20250725_000229_sentiment.csv"
    processed_data = process_and_tag_data(sentiment_csv_to_process)
    if not processed_data.empty:
        print("\nData processing and tagging completed successfully!")
