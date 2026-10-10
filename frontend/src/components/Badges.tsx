import type { Disposition, Severity, State } from "../api/types";
import { DISPOSITION_LABEL, STATE_LABEL, confidenceWord } from "../lib/domain";
import type { ConfidenceWord } from "../lib/domain";
import { Icon } from "./Icon";
import type { IconName } from "./Icon";

const DISPOSITION_ICON: Record<Disposition, IconName> = {
  flag: "flag",
  review: "eye",
  pass: "check-circle",
};

/** The engine proposes; the auditor decides, so the badge reads "Proposed: Flag" by default. */
export function DispositionBadge({
  disposition,
  proposed = false,
}: {
  disposition: Disposition | null;
  proposed?: boolean;
}) {
  if (!disposition) return <span className="ll-badge ll-badge--proposed muted">Pending</span>;
  const badge = (
    <span className={`ll-badge ll-badge--${disposition}`}>
      <Icon name={DISPOSITION_ICON[disposition]} />
      {DISPOSITION_LABEL[disposition]}
    </span>
  );
  if (!proposed) return badge;
  return (
    <span className="ll-badge ll-badge--proposed">
      <span className="ll-badge__prefix">Proposed:</span>
      {badge}
    </span>
  );
}

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export function SeverityChip({ severity, ruleId }: { severity: Severity; ruleId: string }) {
  return (
    <span className={`ll-chip ll-chip--${severity}`}>
      {severity === "critical" && <Icon name="triangle" size={14} />}
      <span className="ll-chip__sev">{SEVERITY_LABEL[severity]}</span>
      <span>{ruleId}</span>
    </span>
  );
}

/** A review signal (MCC-02, EXC-03) is not an exception: a dashed outline with no fill. */
export function SignalChip({ ruleId }: { ruleId: string }) {
  return (
    <span className="ll-chip ll-chip--signal">
      <Icon name="dashed" size={14} />
      <span>{ruleId}</span>
    </span>
  );
}

const WORDS: Record<ConfidenceWord, string> = {
  certain: "Certain",
  likely: "Likely",
  uncertain: "Uncertain",
};

export function ConfidenceBand({
  confidence,
  threshold,
}: {
  confidence: number | null;
  threshold?: number;
}) {
  const word = confidenceWord(confidence, threshold);
  return (
    <span className={`ll-conf ll-conf--${word}`}>
      <span className="ll-conf__bars" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="ll-conf__word">{WORDS[word]}</span>
    </span>
  );
}

const STATE_TONE: Record<State, string> = {
  submitted: "neutral",
  classifying: "neutral",
  auto_approved: "pass",
  in_review: "accent",
  compliance: "critical",
  needs_info: "accent",
  approved: "pass",
  rejected: "neutral-strong",
  failed: "critical",
};

export function StateChip({ state }: { state: State }) {
  return <span className={`state-chip state-chip--${STATE_TONE[state]}`}>{STATE_LABEL[state]}</span>;
}
