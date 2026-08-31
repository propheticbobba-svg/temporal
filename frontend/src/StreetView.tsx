import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { AUTH_FAILURE_EVENT, loadGoogleMaps } from "./maps";
import type { Location } from "./types";

const SEARCH_RADIUS_METERS = 50;
const INITIAL_PITCH = -5;
const INITIAL_ZOOM = 1;
const EMPTY_COPY = "No street-level imagery available for this address";
const MISSING_COORDS_HINT = "Resolved coordinates are required to open Street View.";
const FOCUSABLE_SELECTOR = [
  "button:not([disabled])",
  "[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

// Fixed Non_Exact literal from GeocodeIngester._confidence_for_match.
// Strict equality is valid only because this value is an enum-like constant
// that round-trips Python → JSON → JS unchanged — not a computed score.
const NON_EXACT_CONFIDENCE = 0.7;

type ViewState = "loading" | "ready" | "empty" | "error";

interface StreetView360Props {
  location: Location | null;
  compact?: boolean;
}

interface PanoramaSetup {
  pano: string;
  heading: number;
}

function getFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((element) => {
    return element.tabIndex !== -1 && !element.hasAttribute("disabled") && element.getClientRects().length > 0;
  });
}

export function StreetView({ location, compact = false }: StreetView360Props) {
  const titleId = useId();
  const hintId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const panoramaRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [viewState, setViewState] = useState<ViewState>("loading");
  const [errorMessage, setErrorMessage] = useState("Unable to load street view.");
  const [setup, setSetup] = useState<PanoramaSetup | null>(null);

  const hasCoordinates = location?.latitude != null && location?.longitude != null;
  const showCaveat = location?.confidence === NON_EXACT_CONFIDENCE;

  const close = useCallback(() => {
    setOpen(false);
  }, []);

  function handleOpen() {
    if (!hasCoordinates) {
      return;
    }
    setViewState("loading");
    setErrorMessage("Unable to load street view.");
    setSetup(null);
    setOpen(true);
  }

  useEffect(() => {
    if (!open) {
      return;
    }

    function onAuthFailure() {
      setViewState("error");
      setErrorMessage("Google Maps rejected the API key.");
    }

    window.addEventListener(AUTH_FAILURE_EVENT, onAuthFailure);
    return () => {
      window.removeEventListener(AUTH_FAILURE_EVENT, onAuthFailure);
    };
  }, [open]);

  useEffect(() => {
    if (!open || location?.latitude == null || location.longitude == null) {
      return;
    }

    const latitude = location.latitude;
    const longitude = location.longitude;
    let cancelled = false;

    async function lookupPanorama() {
      try {
        await loadGoogleMaps();
        if (cancelled) {
          return;
        }

        const service = new google.maps.StreetViewService();
        const pending = service.getPanorama(
          { location: { lat: latitude, lng: longitude }, radius: SEARCH_RADIUS_METERS },
          (data, status) => {
            if (cancelled) {
              return;
            }
            if (status === google.maps.StreetViewStatus.ZERO_RESULTS) {
              setSetup(null);
              setViewState("empty");
              return;
            }
            const pano = data?.location?.pano;
            const panoPosition = data?.location?.latLng;
            if (status !== google.maps.StreetViewStatus.OK || !pano || !panoPosition) {
              setSetup(null);
              setErrorMessage("Unable to load street view.");
              setViewState("error");
              return;
            }

            const heading = google.maps.geometry.spherical.computeHeading(
              panoPosition,
              new google.maps.LatLng(latitude, longitude),
            );
            setSetup({ pano, heading });
            setViewState("ready");
          },
        );
        void Promise.resolve(pending).catch(() => undefined);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setSetup(null);
        setErrorMessage(error instanceof Error ? error.message : "Unable to load street view.");
        setViewState("error");
      }
    }

    void lookupPanorama();
    return () => {
      cancelled = true;
    };
  }, [open, location?.latitude, location?.longitude]);

  useEffect(() => {
    if (!open || viewState !== "ready" || !setup || !panoramaRef.current) {
      return;
    }

    const container = panoramaRef.current;
    const panorama = new google.maps.StreetViewPanorama(container, {
      pano: setup.pano,
      pov: {
        heading: setup.heading,
        pitch: INITIAL_PITCH,
      },
      zoom: INITIAL_ZOOM,
      addressControl: false,
      fullscreenControl: true,
      linksControl: true,
      motionTracking: false,
      enableCloseButton: false,
    });

    return () => {
      google.maps.event.clearInstanceListeners(panorama);
      panorama.setVisible(false);
      container.replaceChildren();
    };
  }, [open, viewState, setup]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const trigger = triggerRef.current;
    closeButtonRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }

      const dialog = dialogRef.current;
      if (!dialog) {
        return;
      }

      const focusable = getFocusable(dialog);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === first || !dialog.contains(active)) {
          event.preventDefault();
          last.focus();
        }
        return;
      }
      if (active === last || !dialog.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      trigger?.focus();
    };
  }, [close, open]);

  const modal =
    open && typeof document !== "undefined"
      ? createPortal(
          <div className="fixed inset-0 z-40 grid place-items-center p-6">
            <button
              className="absolute inset-0 border-0 bg-black/55"
              onClick={close}
              type="button"
              aria-label="Close Street View"
            />
            <div
              ref={dialogRef}
              className="relative z-1 flex max-h-[calc(100vh-48px)] w-full max-w-[920px] flex-col overflow-hidden rounded-[20px] border border-line bg-elev"
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
            >
              <header className="flex items-center justify-between gap-4 px-4 py-3.5 sm:px-5">
                <h2 className="m-0 text-lg font-medium tracking-tight text-white" id={titleId}>
                  Street view
                </h2>
                <button
                  ref={closeButtonRef}
                  className="rounded-full bg-transparent px-2.5 py-1.5 text-[0.82rem] font-medium text-muted hover:bg-hover hover:text-ink"
                  onClick={close}
                  type="button"
                >
                  Close
                </button>
              </header>
              <div className="grid min-h-[min(70vh,520px)] bg-bg">
                {viewState === "loading" ? (
                  <p className="grid place-items-center p-8 text-center text-muted" aria-live="polite">
                    Loading street view
                  </p>
                ) : null}
                {viewState === "empty" ? (
                  <p className="grid place-items-center p-8 text-center text-muted">{EMPTY_COPY}</p>
                ) : null}
                {viewState === "error" ? (
                  <p className="grid place-items-center p-8 text-center text-danger" role="alert">
                    {errorMessage}
                  </p>
                ) : null}
                {viewState === "ready" ? (
                  <div className="h-[min(70vh,520px)] w-full" ref={panoramaRef} />
                ) : null}
              </div>
              {showCaveat ? (
                <p className="m-0 px-4 pt-2.5 pb-3.5 text-[0.78rem] text-muted sm:px-5">
                  This view may not be precisely on the property.
                </p>
              ) : null}
            </div>
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      <span className="inline-block" title={hasCoordinates ? undefined : MISSING_COORDS_HINT}>
        <button
          ref={triggerRef}
          className={
            compact
              ? "rounded-full bg-elev px-2.5 py-1 text-xs font-medium text-muted hover:text-ink disabled:text-dim"
              : "rounded-full border border-accent/45 bg-accent/18 px-3.5 py-2 text-[0.82rem] font-medium text-accent hover:border-accent/70 hover:bg-accent/28 disabled:border-line disabled:bg-elev disabled:text-dim"
          }
          disabled={!hasCoordinates}
          onClick={handleOpen}
          type="button"
          aria-describedby={hasCoordinates ? undefined : hintId}
        >
          {compact ? "Street view" : "View 360°"}
        </button>
        {hasCoordinates ? null : (
          <span className="sr-only" id={hintId}>
            {MISSING_COORDS_HINT}
          </span>
        )}
      </span>
      {modal}
    </>
  );
}
