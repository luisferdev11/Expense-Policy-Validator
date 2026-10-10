import type { EventItem } from "../api/types";
import { describeEvent, isHumanEvent } from "../lib/domain";
import { localStamp } from "../lib/format";

/** The audit trail: every event of the receipt, oldest first, with who did it. */
export function Timeline({ events, currentRevision }: { events: EventItem[]; currentRevision: number }) {
  if (events.length === 0) return <p className="muted">No events yet.</p>;
  return (
    <ol className="timeline">
      {events.map((e) => (
        <li key={e.seq} className={`timeline__item${isHumanEvent(e) ? " is-human" : ""}`}>
          <span className="timeline__dot" aria-hidden="true" />
          <div>
            <div className="timeline__text">{describeEvent(e)}</div>
            <div className="timeline__meta ll-num">
              {localStamp(e.at)} · {e.actor}
              {e.revision !== currentRevision ? ` · revision ${e.revision}` : ""}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
