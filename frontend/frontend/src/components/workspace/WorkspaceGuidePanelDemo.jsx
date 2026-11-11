import Icons from "../Icons.jsx";

import "./WorkspaceGuidePanelDemo.css";

function DemoShell({ title, eyebrow, children, className = "" }) {
   return (
      <div className={`workspace-guide-demo ${className}`} aria-hidden="true">
         <div className="workspace-guide-demo-windowbar">
            <div>
               <span />
               <span />
               <span />
            </div>
            <small>{eyebrow}</small>
         </div>
         <div className="workspace-guide-demo-body">
            <div className="workspace-guide-demo-heading">
               <strong>{title}</strong>
               <span>TruthLens Workspace</span>
            </div>
            {children}
         </div>
      </div>
   );
}

function StatusPill({ children, tone = "neutral" }) {
   return <span className={`workspace-guide-demo-pill is-${tone}`}>{children}</span>;
}

function IntakeDemo() {
   return (
      <DemoShell title="Intake" eyebrow="Investigation work">
         <div className="workspace-guide-demo-toolbar">
            <span>Available investigations</span>
            <span className="workspace-guide-demo-select">All classifications⌄</span>
         </div>
         <div className="workspace-guide-demo-record workspace-guide-demo-record--intake">
            <div className="workspace-guide-demo-record-main">
               <div className="workspace-guide-demo-kicker">
                  <StatusPill tone="fact">Available</StatusPill>
                  <StatusPill>Text claim</StatusPill>
               </div>
               <strong>WHO ended the COVID-19 global health emergency in May 2023.</strong>
               <div className="workspace-guide-demo-meta">
                  <span>Evidence · 2 items</span>
                  <span>AI assessment · Fact</span>
               </div>
            </div>
            <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-animated">
               Claim investigation
            </button>
         </div>
      </DemoShell>
   );
}

function InvestigationsDemo() {
   return (
      <DemoShell title="Investigations" eyebrow="Organization workload">
         <div className="workspace-guide-demo-tabs">
            <span className="is-active">All investigations</span>
            <span>My investigations</span>
         </div>
         <div className="workspace-guide-demo-filter-row">
            <span className="workspace-guide-demo-search">Search investigations…</span>
            <span className="workspace-guide-demo-select">Newest first⌄</span>
         </div>
         <div className="workspace-guide-demo-record">
            <div className="workspace-guide-demo-record-main">
               <div className="workspace-guide-demo-kicker">
                  <StatusPill tone="info">Active</StatusPill>
                  <StatusPill>Text claim</StatusPill>
               </div>
               <strong>NASA confirmed the OSIRIS-REx sample capsule landed in Utah.</strong>
               <div className="workspace-guide-demo-meta">
                  <span>Evidence · 3 items</span>
                  <span>Updated recently</span>
               </div>
            </div>
            <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-animated">
               Open investigation
            </button>
         </div>
      </DemoShell>
   );
}

function EvidenceDemo() {
   return (
      <DemoShell title="Evidence Review" eyebrow="Professional evidence review">
         <div className="workspace-guide-demo-split">
            <div className="workspace-guide-demo-queue">
               <small>Review queue</small>
               <div className="workspace-guide-demo-queue-item is-selected">
                  <span><Icons name="paperclip" size={13} /></span>
                  <div>
                     <strong>Submitted source</strong>
                     <small>Reuters · article</small>
                  </div>
               </div>
               <div className="workspace-guide-demo-queue-item">
                  <span><Icons name="paperclip" size={13} /></span>
                  <div>
                     <strong>Supporting source</strong>
                     <small>WHO · report</small>
                  </div>
               </div>
            </div>
            <div className="workspace-guide-demo-detail">
               <div className="workspace-guide-demo-detail-head">
                  <StatusPill tone="info">Pending review</StatusPill>
                  <span>No known threats detected</span>
               </div>
               <strong>Reuters report on the WHO emergency declaration</strong>
               <p>The source is available and relevant to the investigation claim.</p>
               <div className="workspace-guide-demo-source">reuters.com / health / covid-19</div>
               <div className="workspace-guide-demo-actions">
                  <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-success is-animated">
                     Verify evidence
                  </button>
                  <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-danger">
                     Reject evidence
                  </button>
               </div>
            </div>
         </div>
      </DemoShell>
   );
}

function AdjudicationDemo() {
   return (
      <DemoShell title="Adjudication" eyebrow="Authoritative decision">
         <div className="workspace-guide-demo-adjudication">
            <div className="workspace-guide-demo-basis">
               <small>Evidence basis</small>
               <strong>3 of 3 evidence items reviewed</strong>
               <span>Current organization basis complete</span>
            </div>
            <div className="workspace-guide-demo-verdicts">
               <span>Fact</span>
               <span>Fake</span>
               <span className="is-selected is-animated">Misleading</span>
               <span>Satire</span>
            </div>
            <div className="workspace-guide-demo-field">
               <small>Decision rationale</small>
               <div className="workspace-guide-demo-lines">
                  <i />
                  <i />
               </div>
            </div>
            <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-animated">
               Review decision
            </button>
         </div>
      </DemoShell>
   );
}

function DraftingDemo() {
   return (
      <DemoShell title="Drafting" eyebrow="Fact-check editor">
         <div className="workspace-guide-demo-editor">
            <div className="workspace-guide-demo-editor-status">
               <StatusPill tone="warning">Draft</StatusPill>
               <span>Article v1</span>
            </div>
            <label>
               <small>Headline</small>
               <div className="workspace-guide-demo-input">WHO ended the COVID-19 global health emergency in May 2023</div>
            </label>
            <label>
               <small>Article analysis / body</small>
               <div className="workspace-guide-demo-editor-body">
                  <span className="workspace-guide-demo-typing">The reviewed evidence shows that the declaration ended the global health emergency status…</span>
               </div>
            </label>
            <div className="workspace-guide-demo-source-chips">
               <span>WHO source</span>
               <span>Reuters source</span>
            </div>
            <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-animated">Save draft</button>
         </div>
      </DemoShell>
   );
}

function PublishingDemo() {
   return (
      <DemoShell title="Publishing" eyebrow="Publication review queue">
         <div className="workspace-guide-demo-publication">
            <div className="workspace-guide-demo-publication-head">
               <div>
                  <StatusPill tone="warning">Ready for review</StatusPill>
                  <strong>Article v1</strong>
               </div>
               <StatusPill tone="fact">Fact</StatusPill>
            </div>
            <div className="workspace-guide-demo-article">
               <strong>WHO ended the COVID-19 global health emergency in May 2023</strong>
               <div className="workspace-guide-demo-lines">
                  <i />
                  <i />
                  <i />
               </div>
            </div>
            <div className="workspace-guide-demo-actions">
               <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-secondary">
                  Return for rework
               </button>
               <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-success is-animated">
                  Publish fact-check
               </button>
            </div>
         </div>
      </DemoShell>
   );
}

function PublicationsDemo() {
   return (
      <DemoShell title="Publications" eyebrow="Institutional library">
         <div className="workspace-guide-demo-split workspace-guide-demo-split--publication">
            <div className="workspace-guide-demo-queue">
               <small>Published fact-checks</small>
               <div className="workspace-guide-demo-queue-item is-selected">
                  <span><Icons name="book-open" size={13} /></span>
                  <div>
                     <strong>WHO emergency declaration</strong>
                     <small>Published · v1</small>
                  </div>
               </div>
               <div className="workspace-guide-demo-queue-item">
                  <span><Icons name="book-open" size={13} /></span>
                  <div>
                     <strong>OSIRIS-REx landing</strong>
                     <small>Published · v2</small>
                  </div>
               </div>
            </div>
            <div className="workspace-guide-demo-detail">
               <div className="workspace-guide-demo-detail-head">
                  <StatusPill tone="fact">Fact</StatusPill>
                  <span>Published</span>
               </div>
               <strong>WHO emergency declaration</strong>
               <div className="workspace-guide-demo-version-track">
                  <span className="is-current">v1</span>
                  <i />
                  <span>History</span>
               </div>
               <div className="workspace-guide-demo-actions">
                  <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-secondary">
                     Create revision
                  </button>
                  <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-animated">
                     Request correction
                  </button>
               </div>
            </div>
         </div>
      </DemoShell>
   );
}

function CorrectionDemo() {
   return (
      <DemoShell title="Factual Corrections" eyebrow="Post-publication workflow">
         <div className="workspace-guide-demo-correction">
            <div className="workspace-guide-demo-stage-track">
               <span className="is-complete">Request</span>
               <i />
               <span className="is-active is-animated">Review</span>
               <i />
               <span>Proposal</span>
               <i />
               <span>Publish</span>
            </div>
            <div className="workspace-guide-demo-correction-grid">
               <div>
                  <small>Published fact-check</small>
                  <strong>Original publication v1</strong>
                  <StatusPill tone="fact">Fact</StatusPill>
               </div>
               <div>
                  <small>Correction evidence</small>
                  <strong>New authoritative source</strong>
                  <StatusPill tone="info">Reviewed</StatusPill>
               </div>
            </div>
            <div className="workspace-guide-demo-actions">
               <button type="button" tabIndex={-1} className="workspace-guide-demo-action is-animated">
                  Prepare correction proposal
               </button>
            </div>
         </div>
      </DemoShell>
   );
}

function AnalyticsDemo() {
   return (
      <DemoShell title="Analytics" eyebrow="Organization insights">
         <div className="workspace-guide-demo-metrics">
            <div><small>Investigations</small><strong>24</strong><span>+8 this month</span></div>
            <div><small>Resolved</small><strong>18</strong><span>75% completion</span></div>
            <div><small>Publications</small><strong>12</strong><span>Institutional fact-checks</span></div>
         </div>
         <div className="workspace-guide-demo-chart">
            {[36, 52, 44, 68, 74, 60, 84].map((height, index) => (
               <span key={height + index} style={{ "--demo-height": `${height}%`, "--demo-delay": `${index * 0.12}s` }} />
            ))}
         </div>
      </DemoShell>
   );
}

function OrganizationDemo() {
   return (
      <DemoShell title="Organization" eyebrow="Administration">
         <div className="workspace-guide-demo-org">
            <div className="workspace-guide-demo-org-card">
               <span className="workspace-guide-demo-org-logo"><Icons name="shield-user" size={20} /></span>
               <div>
                  <small>Partner Organization</small>
                  <strong>TruthLens Verification Team</strong>
                  <StatusPill tone="fact">Active verification authority</StatusPill>
               </div>
            </div>
            <div className="workspace-guide-demo-member">
               <span>Lead Verifier</span>
               <strong>Verification authority</strong>
               <button type="button" tabIndex={-1}>Manage</button>
            </div>
         </div>
      </DemoShell>
   );
}

function AccountabilityDemo() {
   return (
      <DemoShell title="Accountability History" eyebrow="Professional audit trail">
         <div className="workspace-guide-demo-timeline">
            <div className="is-animated">
               <span><Icons name="check-circle" size={13} /></span>
               <div><strong>Adjudication recorded</strong><small>Lead Verifier · Investigation #1042</small></div>
            </div>
            <div>
               <span><Icons name="file-text" size={13} /></span>
               <div><strong>Fact-check draft updated</strong><small>Researcher · Article v2</small></div>
            </div>
            <div>
               <span><Icons name="book-open" size={13} /></span>
               <div><strong>Publication released</strong><small>Lead Verifier · Public fact-check</small></div>
            </div>
         </div>
      </DemoShell>
   );
}

const DEMOS = {
   intake: IntakeDemo,
   workload: InvestigationsDemo,
   evidence: EvidenceDemo,
   adjudication: AdjudicationDemo,
   drafting: DraftingDemo,
   publishing: PublishingDemo,
   publications: PublicationsDemo,
   "factual-corrections": CorrectionDemo,
   analytics: AnalyticsDemo,
   organization: OrganizationDemo,
   accountability: AccountabilityDemo,
};

export default function WorkspaceGuidePanelDemo({ sectionId }) {
   const Demo = DEMOS[sectionId];
   return Demo ? <Demo /> : null;
}
