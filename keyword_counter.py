import pandas as pd
from collections import Counter
import re
from nltk.corpus import stopwords

# Define four main keyword categories
CATEGORY_KEYWORDS = {
    "food": ["pizza","burger","noodle","ramen","sushi","curry","rice","steak","pasta","bbq","fish","chicken","beef","pork","salad","dessert"],
    "taste": ["spicy","sweet","salty","sour","bitter","fresh","oily","tasty","delicious","yummy","flavor","flavour","taste"],
    "service": ["friendly","rude","quick","slow","attentive","staff","waiter","waitress","helpful","service"],
    "environment": ["clean","dirty","cozy","noisy","romantic","quiet","atmosphere","decor","place","ambience"]
}

def assign_category(word):
    """Assign a word to a predefined category, otherwise 'other'."""
    for category, keywords in CATEGORY_KEYWORDS.items():
        if word in keywords:
            return category
    return "other"


def count_words_in_csv(file_path, column_name="review_text",
                       output_all="all_word_frequencies.csv",
                       output_filtered="filtered_keywords.csv",
                       output_categorized="keywords_by_category.csv",
                       min_freq=10, max_freq=5000):
    """
    Count word frequencies in a CSV file and save:
    1. All word frequencies
    2. Filtered keywords (remove stopwords, very rare and overly common words)
    3. Categorized keywords based on simple dictionaries
    """

    # Load CSV file
    df = pd.read_csv(file_path)

    # Merge all rows in the target column into one big text
    text = " ".join(df[column_name].dropna().astype(str)).lower()

    # Extract words using regex (alphabetic only)
    words = re.findall(r"\b[a-zA-Z']+\b", text)

    # Count frequencies
    counter = Counter(words)

    # Save all words with frequency
    all_words = pd.DataFrame(counter.items(), columns=["word", "frequency"])
    all_words = all_words.sort_values(by="frequency", ascending=False)
    all_words.to_csv(output_all, index=False, encoding="utf-8-sig")
    print(f"All word frequencies saved to {output_all}")

    # Load stopwords from NLTK
    stop_words = set(stopwords.words("english"))

    # Apply filtering: remove stopwords, short words, and very rare/common words
    filtered = all_words.copy()
    filtered = filtered[~filtered['word'].isin(stop_words)]
    filtered = filtered[filtered['word'].str.len() > 2]
    filtered = filtered[(filtered['frequency'] >= min_freq) &
                        (filtered['frequency'] <= max_freq)]
    filtered.to_csv(output_filtered, index=False, encoding="utf-8-sig")
    print(f"Filtered keywords saved to {output_filtered} ({len(filtered)} words)")

    # Categorize words
    filtered["category"] = filtered["word"].apply(assign_category)
    filtered.to_csv(output_categorized, index=False, encoding="utf-8-sig")
    print(f"Categorized keywords saved to {output_categorized}")

    return filtered


if __name__ == "__main__":
    csv_file = "birmingham_restaurants_20250818_231548_sentiment.csv"  # Change to your file
    count_words_in_csv(
        csv_file,
        column_name="review_text"
    )
