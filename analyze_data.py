import pandas as pd
import os

# --- Configure your processed CSV file path ---
# This is the file output by data_processor.py
PROCESSED_CSV_FILENAME = "birmingham_restaurants_20250725_000229_processed.csv"


# ------------------------------------

def analyze_review_counts(filename):
    if not os.path.exists(filename):
        print(f"Error: File '{filename}' not found. Please check the file path and name.")
        return

    try:
        df = pd.read_csv(filename, encoding='utf-8-sig', engine='python')

        # Ensure total_reviews is a numeric type
        df['total_reviews'] = pd.to_numeric(df['total_ratings'], errors='coerce').fillna(0).astype(int)

        print(f"\n--- Analyzing review count distribution for restaurants in '{filename}' ---")

        # Display basic statistics
        print("\nBasic statistics for review counts (total_reviews):")
        print(df['total_reviews'].describe())

        # Display the restaurants with the highest and lowest review counts
        print("\nTop 10 restaurants with the most reviews:")
        print(df.sort_values(by='total_reviews', ascending=False).head(10)[['restaurant_name', 'total_reviews']])

        print("\nTop 10 restaurants with the fewest reviews (non-zero):")
        print(df[df['total_reviews'] > 0].sort_values(by='total_reviews', ascending=True).head(10)[
                  ['restaurant_name', 'total_reviews']])

        # Check the number of restaurants at different thresholds
        print(f"\n--- Number of restaurants at different review count thresholds ---")
        thresholds = [1, 5, 10, 20, 30, 50, 60, 100]
        for threshold in thresholds:
            count = df[df['total_reviews'] >= threshold].shape[0]
            total_restaurants = df.shape[0]
            percentage = (count / total_restaurants * 100) if total_restaurants > 0 else 0
            print(f"Number of restaurants with >= {threshold} reviews: {count} ({percentage:.2f}%)")

    except Exception as e:
        print(f"Error analyzing review counts: {e}")
        print("Please check the file content or format.")


if __name__ == "__main__":
    analyze_review_counts(PROCESSED_CSV_FILENAME)