import type { Finding, ReviewSignal } from "../api/types";
import { findingTitle, policyDocName } from "../lib/domain";
import { SeverityChip, SignalChip } from "./Badges";

export function FindingCard({ finding }: { finding: Finding }) {
  const computed = Object.entries(finding.computed);
  return (
    <article className={`ll-finding ll-finding--${finding.severity}`} aria-label={`Finding ${finding.rule_id}`}>
      <div className="ll-finding__head">
        <SeverityChip severity={finding.severity} ruleId={finding.rule_id} />
        <h4 className="ll-finding__title">{findingTitle(finding)}</h4>
      </div>
      <div className="ll-finding__meta">
        {policyDocName(finding.policy_doc)} · {finding.line_ids.length > 0 ? `lines ${finding.line_ids.join(", ")}` : "whole receipt"}
      </div>
      <blockquote className="ll-finding__quote">
        {finding.evidence}
        <cite>
          Policy text · {finding.rule_id} · {finding.policy_doc}
        </cite>
      </blockquote>
      {(finding.decisions.length > 0 || computed.length > 0) && (
        <ol className="ll-finding__steps">
          {computed.map(([k, v]) => (
            <li key={k}>
              {k.replace(/_/g, " ")}: {v}
            </li>
          ))}
          {finding.decisions.map((d) => (
            <li key={d}>Policy decision {d}</li>
          ))}
        </ol>
      )}
    </article>
  );
}

export function SignalCard({ signal }: { signal: ReviewSignal }) {
  return (
    <article className="signal-card" aria-label={`Review signal ${signal.rule_id}`}>
      <div className="ll-finding__head">
        <SignalChip ruleId={signal.rule_id} />
        <span className="signal-card__label">Needs a person to look</span>
      </div>
      <p className="signal-card__text">{signal.reason}</p>
      <div className="ll-finding__meta">
        {policyDocName(signal.policy_doc)}
        {signal.line_ids.length > 0 ? ` · lines ${signal.line_ids.join(", ")}` : ""}
      </div>
    </article>
  );
}
