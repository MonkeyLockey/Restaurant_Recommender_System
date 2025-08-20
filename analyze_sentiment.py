import pandas as pd
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import os
import json # Import json module to handle JSON string for opening hours

def run_sentiment_analysis():
    # --- Configure your CSV file path ---
    # Please replace the file path here with the actual name of your scraped review CSV file.
    # For example: "birmingham_restaurants_20240718_134530.csv"
    csv_filename = "birmingham_restaurants_20250818_231548.csv"
    # -----------------------------------

    # Check if the file exists
    if not os.path.exists(csv_filename):
        print(f"Error: File '{csv_filename}' not found. Please check the file path and name.")
        return

    # Load the CSV file using pandas
    try:
        # Use utf-8-sig encoding to handle BOM, engine='python' for better compatibility
        df = pd.read_csv(csv_filename, encoding='utf-8-sig', engine='python')
        print(f"Successfully loaded {len(df)} review data entries.")
        print("\nLoaded data preview:")
        print(df.head())
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        print("Please check the file encoding or content format.")
        return

    # Ensure 'review_text' column is of string type and handle missing values
    if 'review_text' in df.columns:
        df['review_text'] = df['review_text'].astype(str).fillna('')
        print("\nReview text preprocessing complete (handled missing values).")
    else:
        print("Error: 'review_text' column not found in the CSV file. Please check the CSV format.")
        return

    # Initialize the VADER sentiment analyzer
    analyzer = SentimentIntensityAnalyzer()

    # Create columns to store sentiment scores
    df['sentiment_compound'] = 0.0
    df['sentiment_neg'] = 0.0
    df['sentiment_neu'] = 0.0
    df['sentiment_pos'] = 0.0
    df['sentiment_label'] = '' # Add a new sentiment label column

    # Perform sentiment analysis on each review
    print("\nStarting sentiment analysis...")
    for index, row in df.iterrows():
        review_text = row['review_text']
        if review_text: # Only analyze non-empty reviews
            vs = analyzer.polarity_scores(review_text)
            df.loc[index, 'sentiment_compound'] = vs['compound']
            df.loc[index, 'sentiment_neg'] = vs['neg']
            df.loc[index, 'sentiment_neu'] = vs['neu']
            df.loc[index, 'sentiment_pos'] = vs['pos']

            # Determine sentiment label based on compound score
            if vs['compound'] >= 0.05:
                df.loc[index, 'sentiment_label'] = 'Positive'
            elif vs['compound'] <= -0.05:
                df.loc[index, 'sentiment_label'] = 'Negative'
            else:
                df.loc[index, 'sentiment_label'] = 'Neutral'
        else:
            # For empty reviews, set to neutral or no sentiment
            df.loc[index, 'sentiment_label'] = 'No Review'

    print("Sentiment analysis complete!")
    print("\nData preview with sentiment scores:")
    print(df[['review_text', 'sentiment_neg', 'sentiment_neu', 'sentiment_pos', 'sentiment_compound', 'sentiment_label']].head())

    # --- Further analysis and visualization (optional) ---
    print("\nSentiment label distribution:")
    print(df['sentiment_label'].value_counts())

    print("\nAverage sentiment score by restaurant name (top 5 shown):")
    if 'restaurant_name' in df.columns:
        # First, handle potentially duplicated place_ids to ensure average sentiment is calculated once per unique place.
        # Here, it's assumed you want to calculate the average sentiment by 'place_id'.
        # If a place has multiple reviews, we take the average sentiment of these reviews.
        unique_places_df = df.groupby('place_id').agg(
            restaurant_name=('restaurant_name', 'first'), # Take the first name
            avg_sentiment_compound=('sentiment_compound', 'mean') # Calculate average sentiment
        ).reset_index()

        avg_sentiment_per_place = unique_places_df.sort_values(by='avg_sentiment_compound', ascending=False)
        print(avg_sentiment_per_place[['restaurant_name', 'avg_sentiment_compound']].head(5))
        print("\nAverage sentiment score by restaurant name (bottom 5 shown):")
        print(avg_sentiment_per_place[['restaurant_name', 'avg_sentiment_compound']].tail(5))
    else:
        print("The CSV file does not contain a 'restaurant_name' column, cannot group by place.")
    # ------------------------------------

    # Save the data with sentiment scores to a new CSV file
    output_sentiment_csv = csv_filename.replace(".csv", "_sentiment.csv")
    df.to_csv(output_sentiment_csv, index=False, encoding='utf-8-sig')
    print(f"\nData with sentiment analysis results saved to: {output_sentiment_csv}")


if __name__ == "__main__":
    run_sentiment_analysis()