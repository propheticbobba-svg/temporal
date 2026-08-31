const SCRIPT_ID = "google-maps-js";
const CALLBACK_NAME = "__temporalGoogleMapsReady";
export const AUTH_FAILURE_EVENT = "temporal-maps-auth-failure";

const LIBRARIES = "places,streetView,geometry";

let mapsLoadPromise: Promise<void> | null = null;

export function isMapsReady(): boolean {
  return Boolean(
    window.google?.maps?.StreetViewService &&
      window.google.maps.geometry?.spherical &&
      window.google.maps.places?.AutocompleteSuggestion,
  );
}

function cleanupFailedScript(): void {
  document.getElementById(SCRIPT_ID)?.remove();
  delete window.__temporalGoogleMapsReady;
}

export function loadGoogleMaps(): Promise<void> {
  if (isMapsReady()) {
    return Promise.resolve();
  }
  if (mapsLoadPromise) {
    return mapsLoadPromise;
  }

  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY?.trim();
  if (!apiKey) {
    return Promise.reject(new Error("Google Maps is not configured."));
  }

  mapsLoadPromise = new Promise<void>((resolve, reject) => {
    const previousAuthFailure = window.gm_authFailure;
    window.gm_authFailure = () => {
      previousAuthFailure?.();
      window.dispatchEvent(new Event(AUTH_FAILURE_EVENT));
      if (!isMapsReady()) {
        cleanupFailedScript();
        reject(new Error("Google Maps rejected the API key."));
      }
    };

    if (document.getElementById(SCRIPT_ID) && isMapsReady()) {
      resolve();
      return;
    }

    window.__temporalGoogleMapsReady = () => {
      delete window.__temporalGoogleMapsReady;
      if (isMapsReady()) {
        resolve();
        return;
      }
      cleanupFailedScript();
      reject(new Error("Unable to load Google Maps."));
    };

    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.async = true;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&loading=async&libraries=${LIBRARIES}&callback=${CALLBACK_NAME}`;
    script.onerror = () => {
      cleanupFailedScript();
      reject(new Error("Unable to load Google Maps."));
    };
    document.head.appendChild(script);
  }).catch((error: unknown) => {
    mapsLoadPromise = null;
    throw error;
  });

  return mapsLoadPromise;
}
