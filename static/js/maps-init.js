// Dynamically load Google Maps API
(function loadGMaps() {
  const meta = document.getElementById('gmaps-config');
  const key = meta?.dataset?.key;
  const callback = meta?.dataset?.callback;

  if (!key) {
    console.error("Maps-init: Google Maps API key not found in meta tag. Please set GOOGLE_MAPS_API_KEY in app.py.");
    return;
  }
  if (!callback) {
      console.error("Maps-init: Google Maps API callback function not found in meta tag. Please ensure meta tag contains data-callback='initMap'.");
      return;
  }

  const s = document.createElement('script');
  s.src = `https://maps.googleapis.com/maps/api/js?key=${key}&callback=${callback}&language=en`;
  s.async = true;
  s.defer = true;
  document.head.appendChild(s);
  console.log("Maps-init: Google Maps API script added to head.");
})();

let map, geocoder;
window.markers = [];
window.userActiveLocation = null;

const DEFAULT_NEARBY_RADIUS = 1000; // meters

function getSearchRadius() {
    const radiusInput = document.getElementById('user_radius_input');
    if (radiusInput && radiusInput.value) {
        const radius = parseInt(radiusInput.value, 10);
        if (!isNaN(radius) && radius > 0) {
            console.log(`Maps-init: User-defined radius: ${radius} meters.`);
            return radius;
        }
    }
    console.log(`Maps-init: Using default radius: ${DEFAULT_NEARBY_RADIUS} meters.`);
    return DEFAULT_NEARBY_RADIUS;
}

window.initMap = function() {
  console.log("Maps-init: initMap called, initializing map...");

  const mapDiv = document.getElementById("map");

  if (!mapDiv) {
    console.warn("Maps-init: Map element not ready. Retrying in 100ms.");
    setTimeout(window.initMap, 100);
    return;
  }

  geocoder = new google.maps.Geocoder();
  map = new google.maps.Map(mapDiv, {
    center: { lat: 52.4862, lng: -1.8904 }, // Birmingham default
    zoom: 13,
  });
  console.log("Maps-init: Map initialized.");

  const initialSelectedLocationSource = window.initialSelectedLocationSource || 'current_location';
  const initialUserLocationInput = window.initialUserLocationInput || '';
  const initialUserRadiusInput = window.initialUserRadiusInput || '';
  console.log(`Maps-init: Initial location source: ${initialSelectedLocationSource}`);
  console.log(`Maps-init: Initial manual input: '${initialUserLocationInput}'`);

  const currentRadio = document.getElementById('current_location_radio');
  const manualRadio = document.getElementById('manual_input_radio');
  const manualLocationInput = document.getElementById('user_location_input');
  const userRadiusInput = document.getElementById('user_radius_input');

  if (currentRadio) currentRadio.checked = (initialSelectedLocationSource === 'current_location');
  if (manualRadio) manualRadio.checked = (initialSelectedLocationSource === 'manual_input');
  if (manualLocationInput) manualLocationInput.value = initialUserLocationInput;
  if (userRadiusInput) userRadiusInput.value = initialUserRadiusInput;

  window.toggleLocationInput();

  if (window.initialRecommendations && window.initialRecommendations.length > 0) {
      console.log("Maps-init: Found initial recommendations, placing markers...");
      window.placeRestaurantMarkers(window.initialRecommendations);
  } else {
      console.log("Maps-init: No initial recommendations found.");
  }
};

window.toggleLocationInput = function() {
  const manualLocationInput = document.getElementById('user_location_input');
  const manualInputRadio = document.getElementById('manual_input_radio');

  if (!manualLocationInput || !manualInputRadio) {
      console.warn("Maps-init: toggleLocationInput: Manual input elements not found.");
      return;
  }

  if (manualInputRadio.checked) {
    manualLocationInput.disabled = false;
    manualLocationInput.focus();
    console.log("Maps-init: Manual input mode enabled.");
    if (manualLocationInput.value) {
        window.geocodeAndUseLocation(manualLocationInput.value);
    } else {
        window.clearUserLocationMarker();
        document.getElementById('top-nearby-list-container').innerHTML = `
            <div class="text-center text-gray-500 py-4">
                <p>Please enter a location to search nearby restaurants.</p>
            </div>
        `;
        window.userActiveLocation = null;
        document.getElementById('user_lat').value = '';
        document.getElementById('user_lng').value = '';
    }
  } else {
    manualLocationInput.disabled = true;
    manualLocationInput.value = '';
    console.log("Maps-init: Current location mode enabled.");
    window.tryGeolocation();
  }
};

window.clearUserLocationMarker = function() {
    console.log("Maps-init: Clearing user location marker...");
    window.markers = window.markers.filter(marker => {
        if (marker.getTitle() === "Your location") {
            marker.setMap(null);
            console.log("Maps-init: Old user location marker cleared.");
            return false;
        }
        return true;
    });
};

window.placeUserLocationMarker = function(location) {
    window.clearUserLocationMarker();

    let latLngObject;
    if (location && typeof location.lat === 'function' && typeof location.lng === 'function') {
        latLngObject = location;
    } else if (location && typeof location.lat === 'number' && typeof location.lng === 'number') {
        latLngObject = new google.maps.LatLng(location.lat, location.lng);
    } else {
        console.error("Maps-init: placeUserLocationMarker: Invalid location object", location);
        return;
    }

    map.setCenter(latLngObject);
    const userMarker = new google.maps.Marker({
        position: latLngObject,
        map: map,
        title: "Your location",
        icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 6,
            fillColor: "#4285F4",
            fillOpacity: 1,
            strokeColor: "white",
            strokeWeight: 2,
        },
    });
    window.markers.push(userMarker);
    window.userActiveLocation = latLngObject;
    console.log(`Maps-init: User location marker placed. Lat ${latLngObject.lat()}, Lng ${latLngObject.lng()}`);

    document.getElementById('user_lat').value = latLngObject.lat();
    document.getElementById('user_lng').value = latLngObject.lng();
    console.log(`Maps-init: Hidden fields updated: user_lat=${latLngObject.lat()}, user_lng=${latLngObject.lng()}`);
};

window.tryGeolocation = function() {
  const box = document.getElementById('top-nearby-list-container');
  if (!navigator.geolocation) {
    box.innerHTML = `<div class="text-center text-red-500 py-4">Your browser does not support geolocation. Please enter your location manually.</div>`;
    console.warn("Maps-init: Geolocation not supported by browser.");
    window.userActiveLocation = null;
    document.getElementById('user_lat').value = '';
    document.getElementById('user_lng').value = '';
    return;
  }

  box.innerHTML = `<div class="text-center text-gray-500 py-4">Loading nearby restaurants using your current location...</div>`;
  console.log("Maps-init: Trying geolocation...");
  navigator.geolocation.getCurrentPosition(pos => {
    const geoLoc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    console.log(`Maps-init: Geolocation success: Lat ${geoLoc.lat}, Lng ${geoLoc.lng}`);
    window.placeUserLocationMarker(geoLoc);
    window.fetchNearbyRestaurants(geoLoc.lat, geoLoc.lng, getSearchRadius());
  }, err => {
    console.error('Maps-init: Geolocation error: ', err);
    let msg = 'Failed to get location.';
    if (err.code === err.PERMISSION_DENIED) {
        msg = 'Permission denied. Please allow location access or enter manually.';
        console.error("Maps-init: Permission denied.");
    } else if (err.code === err.POSITION_UNAVAILABLE) {
        msg = 'Location unavailable. Please try again later.';
        console.error("Maps-init: Position unavailable.");
    } else if (err.code === err.TIMEOUT) {
        msg = 'Location request timed out. Please try again.';
        console.error("Maps-init: Timeout.");
    }
    box.innerHTML = `<div class="text-center text-red-500 py-4">${msg}</div>`;
    window.userActiveLocation = null;
    document.getElementById('user_lat').value = '';
    document.getElementById('user_lng').value = '';
  });
};

window.geocodeAndUseLocation = function(address) {
  if (!address) {
      document.getElementById('top-nearby-list-container').innerHTML = `
          <div class="text-center text-gray-500 py-4">
              <p>Please enter a location to search nearby restaurants.</p>
          </div>
      `;
      window.clearUserLocationMarker();
      window.userActiveLocation = null;
      document.getElementById('user_lat').value = '';
      document.getElementById('user_lng').value = '';
      console.log("Maps-init: Manual address is empty.");
      return;
  }

  document.getElementById('top-nearby-list-container').innerHTML = `
      <div class="text-center text-gray-500 py-4">
          <p>Geocoding "${address}" and loading nearby restaurants...</p>
      </div>
  `;
  console.log(`Maps-init: Geocoding address '${address}'...`);

  geocoder.geocode({ 'address': address }, function(results, status) {
    if (status == 'OK' && results[0]) {
      const geoLoc = results[0].geometry.location;
      console.log(`Maps-init: Geocode success: Lat ${geoLoc.lat()}, Lng ${geoLoc.lng()}`);
      window.placeUserLocationMarker(geoLoc);
      window.fetchNearbyRestaurants(geoLoc.lat(), geoLoc.lng(), getSearchRadius());
    } else {
      console.error('Maps-init: Geocode failed: ' + status);
      document.getElementById('top-nearby-list-container').innerHTML = `
          <div class="text-center text-red-500 py-4">
              <p>Error: Could not locate address "${address}". Please check spelling.</p>
          </div>
      `;
      window.clearUserLocationMarker();
      window.userActiveLocation = null;
      document.getElementById('user_lat').value = '';
      document.getElementById('user_lng').value = '';
    }
  });
};

window.placeRestaurantMarkers = function(restaurantData) {
    console.log("Maps-init: Placing restaurant markers...");
    window.markers = window.markers.filter(marker => {
        if (marker.getTitle() !== "Your location") {
            marker.setMap(null);
            return false;
        }
        return true;
    });

    if (!restaurantData || restaurantData.length === 0) {
        console.log("Maps-init: No restaurant data to place.");
        return;
    }

    restaurantData.forEach((r) => {
        if (r.latitude && r.longitude) {
            const marker = new google.maps.Marker({
                position: { lat: r.latitude, lng: r.longitude },
                map: map,
                title: r.restaurant_name,
            });
            const infoWindow = new google.maps.InfoWindow({
                content: `
                    <div>
                        <strong>
                            <a href="https://www.google.com/maps/place/?q=place_id:${r.place_id}" target="_blank" style="color: #6366F1; text-decoration: underline;">
                                ${r.restaurant_name}
                            </a>
                        </strong><br>
                        ${r.address}<br>
                        ⭐ ${typeof r.avg_rating === 'number' ? r.avg_rating.toFixed(1) : 'N/A'} (${r.total_ratings})
                    </div>
                `
            });
            marker.addListener("click", () => {
                infoWindow.open(map, marker);
            });
            window.markers.push(marker);
        }
    });
    console.log(`Maps-init: Placed ${restaurantData.length} restaurant markers.`);

    if (window.markers.length > 0) {
        const bounds = new google.maps.LatLngBounds();
        window.markers.forEach(marker => bounds.extend(marker.getPosition()));
        map.fitBounds(bounds);
        console.log("Maps-init: Map bounds adjusted to include all markers.");
    }
};
