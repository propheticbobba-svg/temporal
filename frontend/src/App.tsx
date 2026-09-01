import { usePlaceSession, useReveal, useWorkspace, type WorkspaceView } from "./api/query";
import { Composer, TemporalMark, ThinkField, WorkspaceRail } from "./chrome";
import { PlaceGraph } from "./graph/canvas";
import { StreetView } from "./maps/StreetView";
import { BriefView } from "./overview";

const TABS: WorkspaceView[] = ["graph", "overview"];

export default function App() {
  const { draft, setDraft, address, ticket, open, reset, place, error } = usePlaceSession();
  const brief = place?.brief;
  const location = place?.location ?? null;
  const stage = useReveal(ticket, Boolean(brief), Boolean(error) && !brief);
  const ready = stage === "ready";
  const thinking = stage === "thinking";
  const { view, openOverview, changeView } = useWorkspace(ready ? brief?.address : undefined);

  function goHome() {
    reset();
  }

  return (
    <div className="flex h-full bg-bg">
      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="relative z-10 flex min-h-12 items-center gap-3 px-4 pt-3.5 min-[880px]:px-6 min-[880px]:pt-4">
          <TemporalMark onHome={goHome} replay={ticket} />
          {ready && brief ? (
            <div className="ml-auto flex items-center gap-2">
              <div className="flex gap-0.5 min-[880px]:hidden" role="tablist" aria-label="Workspace">
                {TABS.map((item) => (
                  <button
                    key={item}
                    aria-selected={view === item}
                    className={`rounded-full px-2 py-1 text-xs font-medium capitalize ${
                      view === item ? "bg-elev text-ink" : "text-dim"
                    }`}
                    onClick={() => changeView(item)}
                    role="tab"
                    type="button"
                  >
                    {item}
                  </button>
                ))}
              </div>
              <StreetView compact location={location} />
            </div>
          ) : null}
        </header>

        {ready ? (
          <>
            <div
              className={
                view === "graph"
                  ? "relative z-10 flex min-h-0 flex-1 flex-col overflow-hidden p-0"
                  : "relative z-10 flex min-h-0 flex-1 flex-col overflow-auto px-5 py-2 min-[880px]:px-12"
              }
            >
              {brief && address && view === "graph" ? (
                <PlaceGraph address={address} onOpenOverview={openOverview} />
              ) : null}
              {brief && view === "overview" ? <BriefView brief={brief} location={location} /> : null}
            </div>
            <div className="relative z-10 flex justify-center px-4 pt-2 pb-7 min-[880px]:px-12 min-[880px]:pb-8">
              <Composer
                address={draft}
                docked
                error={error}
                isLoading={false}
                onAddressChange={setDraft}
                onSubmit={open}
              />
            </div>
          </>
        ) : (
          <div className="relative z-10 flex min-h-0 flex-1 flex-col px-4 min-[880px]:px-12">
            <div className="relative min-h-0 flex-1 overflow-hidden">
              <ThinkField thinking={thinking} />
            </div>
            <div className="relative z-20 flex justify-center pt-3 pb-8">
              <Composer
                address={draft}
                docked={false}
                error={error}
                isLoading={thinking}
                onAddressChange={setDraft}
                onSubmit={open}
              />
            </div>
          </div>
        )}
      </main>

      {ready && brief ? <WorkspaceRail view={view} onChange={changeView} /> : null}
    </div>
  );
}
