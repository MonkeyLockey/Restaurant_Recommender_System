import unittest
from unittest.mock import patch, MagicMock
import os
import csv
from datetime import datetime
import json  # 新增導入

# 從 scraper 套件中導入 RestaurantScraper
from scraper.core import RestaurantScraper


class TestRestaurantScraper(unittest.TestCase):

    def setUp(self):
        self.api_key = "FAKE_API_KEY"
        self.test_history_csv = "test_history.csv"
        if os.path.exists(self.test_history_csv):
            os.remove(self.test_history_csv)

        self.patcher = patch('googlemaps.Client')
        self.MockGoogleMapsClient = self.patcher.start()

        self.scraper = RestaurantScraper(self.api_key, existing_csv_filename=self.test_history_csv)
        self.mock_gmaps_instance = self.scraper.gmaps

    def tearDown(self):
        if os.path.exists(self.test_history_csv):
            os.remove(self.test_history_csv)
        for f in os.listdir('.'):
            if f.startswith("birmingham_restaurants_") and f.endswith(".csv"):
                os.remove(f)
        self.patcher.stop()

    def test_search_restaurants_basic(self):
        self.mock_gmaps_instance.geocode.return_value = [
            {'geometry': {'location': {'lat': 52.4862, 'lng': -1.8904}}}
        ]
        self.mock_gmaps_instance.places_nearby.return_value = {
            'results': [
                {'place_id': 'rest1', 'name': 'Test Restaurant 1'},
                {'place_id': 'rest2', 'name': 'Test Restaurant 2'}
            ],
            'next_page_token': None
        }
        self.mock_gmaps_instance.place.side_effect = [
            {'result': {
                'name': 'Test Restaurant 1', 'rating': 4.5, 'user_ratings_total': 100,
                'formatted_address': 'Addr1', 'reviews': [],
                'opening_hours': {'open_now': True, 'weekday_text': ['Monday: 9 AM - 5 PM']}  # 新增營業時間
            }},
            {'result': {
                'name': 'Test Restaurant 2', 'rating': 4.0, 'user_ratings_total': 50,
                'formatted_address': 'Addr2', 'reviews': [],
                'opening_hours': {'open_now': False, 'weekday_text': ['Tuesday: 10 AM - 6 PM']}  # 新增營業時間
            }}
        ]

        self.scraper.search_restaurants("Test Location", limit=2, place_types=['restaurant'])

        self.assertEqual(self.scraper.api_call_count, 1 + 1 + 2)
        self.assertEqual(self.mock_gmaps_instance.geocode.call_count, 1)
        self.assertEqual(self.mock_gmaps_instance.places_nearby.call_count, 1)
        self.assertEqual(self.mock_gmaps_instance.place.call_count, 2)

        self.assertEqual(len(self.scraper.restaurants_data), 2)
        self.assertEqual(len(self.scraper.processed_place_ids), 2)
        self.assertIn('rest1', self.scraper.processed_place_ids)
        self.assertIn('rest2', self.scraper.processed_place_ids)

        # 新增斷言: 驗證營業時間
        self.assertEqual(self.scraper.restaurants_data[0]['opening_hours'],
                         json.dumps(['Monday: 9 AM - 5 PM'], ensure_ascii=False))
        self.assertEqual(self.scraper.restaurants_data[1]['opening_hours'],
                         json.dumps(['Tuesday: 10 AM - 6 PM'], ensure_ascii=False))

    def test_search_restaurants_pagination_and_deduplication(self):
        self.mock_gmaps_instance.geocode.return_value = [
            {'geometry': {'location': {'lat': 52.4862, 'lng': -1.8904}}}
        ]
        self.mock_gmaps_instance.places_nearby.side_effect = [
            {
                'results': [
                    {'place_id': 'rest1', 'name': 'Rest A'},
                    {'place_id': 'rest2', 'name': 'Rest B'}
                ],
                'next_page_token': 'page2_token'
            },
            {
                'results': [
                    {'place_id': 'rest2', 'name': 'Rest B'},
                    {'place_id': 'rest3', 'name': 'Rest C'}
                ],
                'next_page_token': None
            }
        ]
        self.mock_gmaps_instance.place.side_effect = [
            {'result': {
                'name': 'Rest A', 'rating': 4.0, 'user_ratings_total': 10,
                'formatted_address': 'AddrA', 'reviews': [],
                'opening_hours': {'weekday_text': ['Mon-Fri: 9-17']}
            }},
            {'result': {
                'name': 'Rest B', 'rating': 4.2, 'user_ratings_total': 20,
                'formatted_address': 'AddrB', 'reviews': [],
                'opening_hours': {'weekday_text': ['Mon-Sun: 10-22']}
            }},
            {'result': {
                'name': 'Rest C', 'rating': 3.5, 'user_ratings_total': 5,
                'formatted_address': 'AddrC', 'reviews': [],
                'opening_hours': {'weekday_text': ['Sat-Sun: 12-20']}
            }}
        ]

        self.scraper.search_restaurants("Test Location", limit=60, place_types=['restaurant'])

        self.assertEqual(self.scraper.api_call_count, 1 + 2 + 3)
        self.assertEqual(self.mock_gmaps_instance.geocode.call_count, 1)
        self.assertEqual(self.mock_gmaps_instance.places_nearby.call_count, 2)
        self.assertEqual(self.mock_gmaps_instance.place.call_count, 3)

        self.assertEqual(len(self.scraper.restaurants_data), 3)
        self.assertEqual(len(self.scraper.processed_place_ids), 3)
        self.assertIn('rest1', self.scraper.processed_place_ids)
        self.assertIn('rest2', self.scraper.processed_place_ids)
        self.assertIn('rest3', self.scraper.processed_place_ids)

        # 新增斷言: 驗證營業時間
        self.assertEqual(self.scraper.restaurants_data[0]['opening_hours'],
                         json.dumps(['Mon-Fri: 9-17'], ensure_ascii=False))
        self.assertEqual(self.scraper.restaurants_data[1]['opening_hours'],
                         json.dumps(['Mon-Sun: 10-22'], ensure_ascii=False))
        self.assertEqual(self.scraper.restaurants_data[2]['opening_hours'],
                         json.dumps(['Sat-Sun: 12-20'], ensure_ascii=False))

    def test_search_restaurants_multiple_types_and_deduplication(self):
        self.mock_gmaps_instance.geocode.return_value = [
            {'geometry': {'location': {'lat': 52.4862, 'lng': -1.8904}}}
        ]

        self.mock_gmaps_instance.places_nearby.side_effect = [
            {
                'results': [
                    {'place_id': 'rest_A', 'name': 'Restaurant A'},
                    {'place_id': 'rest_B', 'name': 'Restaurant B'}
                ],
                'next_page_token': None
            },
            {
                'results': [
                    {'place_id': 'rest_B', 'name': 'Bar B (same as Restaurant B)'},
                    {'place_id': 'bar_C', 'name': 'Bar C'}
                ],
                'next_page_token': None
            }
        ]

        self.mock_gmaps_instance.place.side_effect = [
            {'result': {
                'name': 'Restaurant A', 'rating': 4.0, 'user_ratings_total': 10,
                'formatted_address': 'AddrA', 'reviews': [],
                'opening_hours': {'weekday_text': ['Mon-Fri: 8 AM - 4 PM']}
            }},
            {'result': {
                'name': 'Restaurant B', 'rating': 4.2, 'user_ratings_total': 20,
                'formatted_address': 'AddrB', 'reviews': [],
                'opening_hours': {'weekday_text': ['Everyday: 11 AM - 10 PM']}
            }},
            {'result': {'name': 'Bar C', 'rating': 3.5, 'user_ratings_total': 5,
                        'formatted_address': 'AddrC', 'reviews': [],
                        'opening_hours': {'weekday_text': ['Mon-Sat: 5 PM - 1 AM']}
                        }}
        ]

        self.scraper.search_restaurants("Test Location Multi", limit=60, place_types=['restaurant', 'bar'])

        self.assertEqual(self.scraper.api_call_count, 1 + 2 + 3)
        self.assertEqual(self.mock_gmaps_instance.geocode.call_count, 1)
        self.assertEqual(self.mock_gmaps_instance.places_nearby.call_count, 2)
        self.assertEqual(self.mock_gmaps_instance.place.call_count, 3)

        self.assertEqual(len(self.scraper.restaurants_data), 3)
        self.assertEqual(len(self.scraper.processed_place_ids), 3)
        self.assertIn('rest_A', self.scraper.processed_place_ids)
        self.assertIn('rest_B', self.scraper.processed_place_ids)
        self.assertIn('bar_C', self.scraper.processed_place_ids)

        names = sorted([r['name'] for r in self.scraper.restaurants_data])
        self.assertEqual(names, ['Bar C', 'Restaurant A', 'Restaurant B'])

        # 新增斷言: 驗證營業時間
        self.assertEqual(self.scraper.restaurants_data[0]['opening_hours'],
                         json.dumps(['Mon-Fri: 8 AM - 4 PM'], ensure_ascii=False))
        self.assertEqual(self.scraper.restaurants_data[1]['opening_hours'],
                         json.dumps(['Everyday: 11 AM - 10 PM'], ensure_ascii=False))
        self.assertEqual(self.scraper.restaurants_data[2]['opening_hours'],
                         json.dumps(['Mon-Sat: 5 PM - 1 AM'], ensure_ascii=False))

    def test_cross_run_deduplication(self):
        first_run_scraper = RestaurantScraper(self.api_key)
        mock_gmaps_instance_for_first_run = first_run_scraper.gmaps

        mock_gmaps_instance_for_first_run.geocode.return_value = [
            {'geometry': {'location': {'lat': 52.4862, 'lng': -1.8904}}}]
        mock_gmaps_instance_for_first_run.places_nearby.side_effect = [
            {
                'results': [
                    {'place_id': 'rest_old_1', 'name': 'Old Rest 1'},
                    {'place_id': 'rest_old_2', 'name': 'Old Rest 2'}
                ],
                'next_page_token': None
            },
            {
                'results': [
                    {'place_id': 'cafe_old_3', 'name': 'Old Cafe 3'}
                ],
                'next_page_token': None
            }
        ]
        mock_gmaps_instance_for_first_run.place.side_effect = [
            {'result': {
                'name': 'Old Rest 1', 'rating': 4.0, 'user_ratings_total': 10,
                'formatted_address': 'AddrOld1', 'reviews': [],
                'opening_hours': {'weekday_text': ['Mon-Fri: 9-17']}
            }},
            {'result': {
                'name': 'Old Rest 2', 'rating': 3.5, 'user_ratings_total': 5,
                'formatted_address': 'AddrOld2', 'reviews': [],
                'opening_hours': {'weekday_text': ['Mon-Sun: 10-22']}
            }},
            {'result': {
                'name': 'Old Cafe 3', 'rating': 4.5, 'user_ratings_total': 15,
                'formatted_address': 'AddrOld3', 'reviews': [],
                'opening_hours': {'weekday_text': ['Everyday: 7-23']}
            }}
        ]

        first_run_scraper.search_restaurants("First Run Location", limit=60, place_types=['restaurant', 'cafe'])
        first_run_scraper.save_to_csv(self.test_history_csv)

        self.assertEqual(len(first_run_scraper.processed_place_ids), 3)
        self.assertIn('rest_old_1', first_run_scraper.processed_place_ids)
        self.assertIn('rest_old_2', first_run_scraper.processed_place_ids)
        self.assertIn('cafe_old_3', first_run_scraper.processed_place_ids)

        self.mock_gmaps_instance.reset_mock()
        self.scraper.api_call_count = 0

        self.scraper = RestaurantScraper(self.api_key, existing_csv_filename=self.test_history_csv)
        self.mock_gmaps_instance = self.scraper.gmaps

        self.assertEqual(len(self.scraper.processed_place_ids), 3)
        self.assertIn('rest_old_1', self.scraper.processed_place_ids)
        self.assertIn('rest_old_2', self.scraper.processed_place_ids)
        self.assertIn('cafe_old_3', self.scraper.processed_place_ids)

        self.mock_gmaps_instance.geocode.return_value = [{'geometry': {'location': {'lat': 52.4862, 'lng': -1.8904}}}]
        self.mock_gmaps_instance.places_nearby.side_effect = [
            {
                'results': [
                    {'place_id': 'rest_old_1', 'name': 'Old Rest 1'},
                    {'place_id': 'rest_new_4', 'name': 'New Rest 4'}
                ],
                'next_page_token': None
            },
            {
                'results': [
                    {'place_id': 'cafe_old_3', 'name': 'Old Cafe 3'},
                    {'place_id': 'cafe_new_5', 'name': 'New Cafe 5'}
                ],
                'next_page_token': None
            }
        ]
        self.mock_gmaps_instance.place.side_effect = [
            {'result': {
                'name': 'New Rest 4', 'rating': 4.8, 'user_ratings_total': 200,
                'formatted_address': 'AddrNew4', 'reviews': [],
                'opening_hours': {'weekday_text': ['Mon-Fri: 6-22']}
            }},
            {'result': {
                'name': 'New Cafe 5', 'rating': 4.0, 'user_ratings_total': 150,
                'formatted_address': 'AddrNew5', 'reviews': [],
                'opening_hours': {'weekday_text': ['Everyday: 8-18']}
            }}
        ]

        self.scraper.search_restaurants("Second Run Location", limit=60, place_types=['restaurant', 'cafe'])

        self.assertEqual(self.scraper.api_call_count, 1 + 2 + 2)
        self.assertEqual(self.mock_gmaps_instance.geocode.call_count, 1)
        self.assertEqual(self.mock_gmaps_instance.places_nearby.call_count, 2)
        self.assertEqual(self.mock_gmaps_instance.place.call_count, 2)

        self.assertEqual(len(self.scraper.restaurants_data), 2)
        self.assertEqual(self.scraper.restaurants_data[0]['name'], 'New Rest 4')
        self.assertEqual(self.scraper.restaurants_data[1]['name'], 'New Cafe 5')

        self.assertEqual(len(self.scraper.processed_place_ids), 5)
        self.assertIn('rest_old_1', self.scraper.processed_place_ids)
        self.assertIn('rest_old_2', self.scraper.processed_place_ids)
        self.assertIn('cafe_old_3', self.scraper.processed_place_ids)
        self.assertIn('rest_new_4', self.scraper.processed_place_ids)
        self.assertIn('cafe_new_5', self.scraper.processed_place_ids)

        # 新增斷言: 驗證營業時間
        self.assertEqual(self.scraper.restaurants_data[0]['opening_hours'],
                         json.dumps(['Mon-Fri: 6-22'], ensure_ascii=False))
        self.assertEqual(self.scraper.restaurants_data[1]['opening_hours'],
                         json.dumps(['Everyday: 8-18'], ensure_ascii=False))


# 運行測試
if __name__ == '__main__':
    unittest.main(argv=sys.argv[:1], exit=False)
