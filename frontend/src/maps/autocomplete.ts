import { useEffect, useRef, useState } from "react";

import { loadGoogleMaps } from "./load";

const DEBOUNCE_MS = 250;
const MIN_CHARS = 3;

export interface AddressSuggestion {
  id: string;
  text: string;
  mainText: string;
  secondaryText: string;
}

function formatText(value: google.maps.places.FormattableText | null | undefined): string {
  return value?.text ?? "";
}

function toSuggestion(
  suggestion: google.maps.places.AutocompleteSuggestion,
  index: number,
): AddressSuggestion | null {
  const prediction = suggestion.placePrediction;
  if (!prediction) {
    return null;
  }
  const text = formatText(prediction.text);
  if (!text) {
    return null;
  }
  return {
    id: prediction.placeId || `prediction-${index}`,
    text,
    mainText: formatText(prediction.mainText) || text,
    secondaryText: formatText(prediction.secondaryText),
  };
}

export function useAddressAutocomplete(query: string, enabled: boolean) {
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const tokenRef = useRef<google.maps.places.AutocompleteSessionToken | null>(null);
  const predictionsRef = useRef(new Map<string, google.maps.places.PlacePrediction>());
  const generationRef = useRef(0);

  useEffect(() => {
    if (!query.trim()) {
      tokenRef.current = null;
    }
  }, [query]);

  useEffect(() => {
    if (!enabled || query.trim().length < MIN_CHARS) {
      setSuggestions([]);
      return;
    }

    let cancelled = false;
    const generation = ++generationRef.current;
    const input = query.trim();

    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          await loadGoogleMaps();
          if (cancelled || generation !== generationRef.current) {
            return;
          }

          if (!tokenRef.current) {
            tokenRef.current = new google.maps.places.AutocompleteSessionToken();
          }

          const response = await google.maps.places.AutocompleteSuggestion.fetchAutocompleteSuggestions({
            input,
            includedRegionCodes: ["us"],
            sessionToken: tokenRef.current,
          });
          if (cancelled || generation !== generationRef.current) {
            return;
          }

          const next: AddressSuggestion[] = [];
          const predictions = new Map<string, google.maps.places.PlacePrediction>();
          response.suggestions.forEach((item, index) => {
            const suggestion = toSuggestion(item, index);
            if (suggestion == null || item.placePrediction == null) {
              return;
            }
            next.push(suggestion);
            predictions.set(suggestion.id, item.placePrediction);
          });
          predictionsRef.current = predictions;
          setSuggestions(next);
        } catch {
          if (cancelled || generation !== generationRef.current) {
            return;
          }
          setSuggestions([]);
        }
      })();
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [enabled, query]);

  async function resolveStreetAddress(suggestion: AddressSuggestion): Promise<string> {
    try {
      await loadGoogleMaps();
      const prediction = predictionsRef.current.get(suggestion.id);
      const place = prediction?.toPlace() ?? new google.maps.places.Place({ id: suggestion.id });
      await place.fetchFields({ fields: ["formattedAddress"] });
      const formatted = place.formattedAddress?.trim();
      if (formatted) {
        return formatted;
      }
    } catch {
      // Keep the prediction label if Place Details fails.
    }
    return suggestion.text;
  }

  function consumeSession() {
    tokenRef.current = null;
    predictionsRef.current = new Map();
    setSuggestions([]);
  }

  return { suggestions, consumeSession, resolveStreetAddress };
}
