import { Spinner } from "./Spinner";

export type ResearchStatus = "pending" | "researching" | "completed" | "failed";

type MilestoneState = "done" | "current" | "upcoming" | "failed";

interface Milestone {
  key: string;
  label: string;
  state: MilestoneState;
}

/**
 * pending / researching / completed / failed という、backendが実際に
 * 保証する4値のstatusだけからマイルストーンを組み立てる。
 * 「検索中→AI生成中」のような、APIが返さない架空の細分化は行わない。
 */
function buildMilestones(status: ResearchStatus): Milestone[] {
  const base = [
    { key: "pending", label: "受付" },
    { key: "researching", label: "処理中" },
  ];

  if (status === "pending") {
    return [
      { ...base[0], state: "current" },
      { ...base[1], state: "upcoming" },
      { key: "completed", label: "完了", state: "upcoming" },
    ];
  }

  if (status === "researching") {
    return [
      { ...base[0], state: "done" },
      { ...base[1], state: "current" },
      { key: "completed", label: "完了", state: "upcoming" },
    ];
  }

  if (status === "completed") {
    return [
      { ...base[0], state: "done" },
      { ...base[1], state: "done" },
      { key: "completed", label: "完了", state: "done" },
    ];
  }

  // failed: pending/researchingには実際に到達した上で終了しているので、
  // その事実だけを表示する(存在しない途中経過を捏造しない)。
  return [
    { ...base[0], state: "done" },
    { ...base[1], state: "done" },
    { key: "completed", label: "終了(失敗)", state: "failed" },
  ];
}

function DotIcon({ state }: { state: MilestoneState }) {
  if (state === "current") {
    return (
      <span className="status-timeline__dot status-timeline__dot--current">
        <Spinner />
      </span>
    );
  }
  if (state === "done") {
    return <span className="status-timeline__dot status-timeline__dot--done">✓</span>;
  }
  if (state === "failed") {
    return <span className="status-timeline__dot status-timeline__dot--failed">✕</span>;
  }
  return <span className="status-timeline__dot status-timeline__dot--upcoming" />;
}

export function StatusTimeline({ status }: { status: ResearchStatus }) {
  const milestones = buildMilestones(status);

  return (
    <div className="status-timeline">
      {milestones.map((milestone, index) => (
        <div className="status-timeline__item" key={milestone.key}>
          <div className="status-timeline__marker-col">
            <DotIcon state={milestone.state} />
            {index < milestones.length - 1 && <div className="status-timeline__line" />}
          </div>
          <span
            className={
              milestone.state === "upcoming"
                ? "status-timeline__label"
                : "status-timeline__label status-timeline__label--active"
            }
          >
            {milestone.label}
          </span>
        </div>
      ))}
    </div>
  );
}
