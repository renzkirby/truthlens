import { useState } from "react";
import {
   Search,
   Scissors,
   Upload,
   Link,
   Target,
   AlertTriangle,
   X,
   MessageCircle,
   Paperclip,
   ThumbsUp,
   ChevronUp,
   ChevronDown,
   Home,
   Globe,
   Settings,
   User,
   TrendingUp,
   CheckCircle2,
   XCircle,
   HelpCircle,
   MoreHorizontal,
   Shield,
   FileText,
   Image,
   Star,
   Lightbulb,
   Eye,
   Trophy,
   Wand2,
   Newspaper,
   Landmark,
   LayoutDashboard,
   Palette,
   Ruler,
   Braces,
   Puzzle,
   Hash,
   ArrowRight,
   ExternalLink,
   Flag,
   BookOpen,
   BarChart2,
   UserCircle,
   BadgeCheck,
   Crosshair,
   ScanLine,
   Users,
   MessageSquare,
   Sparkles,
   Layers,
   PanelLeft,
} from "lucide-react";

// ─── Design Tokens ────────────────────────────────────────────────────────────
const T = {
   indigo: "#4f46e5",
   bg: "#f9fafb",
   surface: "#ffffff",
   green: "#0e9f6e",
   red: "#e02424",
   amber: "#d97706",
   amberBg: "#fef3c7",
   gray: "#6b7280",
   violet: "#7c3aed",
   dark: "#1e1b4b",
};

// ─── Primitives ───────────────────────────────────────────────────────────────

const VerdictBadge = ({ verdict }) => {
   const map = {
      verified: {
         bg: "#d1fae5",
         text: "#065f46",
         border: T.green,
         label: "Verified",
         Icon: CheckCircle2,
      },
      fake: { bg: "#fee2e2", text: "#7f1d1d", border: T.red, label: "Fake / False", Icon: XCircle },
      misleading: {
         bg: T.amberBg,
         text: "#78350f",
         border: T.amber,
         label: "Misleading",
         Icon: AlertTriangle,
      },
      unverified: {
         bg: "#f3f4f6",
         text: "#374151",
         border: T.gray,
         label: "Unverified",
         Icon: HelpCircle,
      },
      satire: { bg: "#ede9fe", text: "#4c1d95", border: T.violet, label: "Satire", Icon: Wand2 },
   };
   const s = map[verdict] || map.unverified;
   return (
      <span
         style={{
            background: s.bg,
            color: s.text,
            border: `1.5px solid ${s.border}`,
            borderRadius: 6,
            padding: "3px 9px",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.03em",
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
         }}>
         <s.Icon
            size={11}
            strokeWidth={2.5}
         />
         {s.label}
      </span>
   );
};

const TrustGauge = ({ score }) => {
   const c = score >= 80 ? T.green : score >= 50 ? T.amber : T.red;
   return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
         <svg
            width={64}
            height={64}
            viewBox="0 0 64 64">
            <circle
               cx={32}
               cy={32}
               r={26}
               fill="none"
               stroke="#e5e7eb"
               strokeWidth={6}
            />
            <circle
               cx={32}
               cy={32}
               r={26}
               fill="none"
               stroke={c}
               strokeWidth={6}
               strokeDasharray={`${(score / 100) * 163.4} 163.4`}
               strokeLinecap="round"
               transform="rotate(-90 32 32)"
            />
            <text
               x={32}
               y={37}
               textAnchor="middle"
               fontSize={13}
               fontWeight={800}
               fill={c}>
               {score}
            </text>
         </svg>
         <span style={{ fontSize: 10, color: T.gray, fontWeight: 600, letterSpacing: "0.06em" }}>
            TRUST SCORE
         </span>
      </div>
   );
};

const Logo = ({ size = 18, bg = T.indigo }) => (
   <div
      style={{
         width: size + 10,
         height: size + 10,
         background: bg,
         borderRadius: Math.round((size + 10) * 0.3),
         display: "flex",
         alignItems: "center",
         justifyContent: "center",
         flexShrink: 0,
      }}>
      <Search
         size={size}
         color="#fff"
         strokeWidth={2.5}
      />
   </div>
);

const Avatar = ({ Icon = User, bg = "#ede9fe", color = T.violet, size = 38 }) => (
   <div
      style={{
         width: size,
         height: size,
         borderRadius: "50%",
         background: bg,
         display: "flex",
         alignItems: "center",
         justifyContent: "center",
         flexShrink: 0,
      }}>
      <Icon
         size={size * 0.44}
         color={color}
         strokeWidth={2}
      />
   </div>
);

const ImgPlaceholder = ({ label = "Snipped image", Icon: Ic = Image }) => (
   <div
      style={{
         width: "100%",
         minHeight: 200,
         background: "linear-gradient(135deg,#e0e7ff,#f3f4f6)",
         display: "flex",
         flexDirection: "column",
         alignItems: "center",
         justifyContent: "center",
         gap: 10,
      }}>
      <div
         style={{
            width: 48,
            height: 48,
            background: "rgba(255,255,255,0.65)",
            borderRadius: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
         }}>
         <Ic
            size={22}
            color={T.gray}
            strokeWidth={1.5}
         />
      </div>
      <span style={{ fontSize: 11, color: T.gray, fontWeight: 600 }}>{label}</span>
   </div>
);

const SLabel = ({ children }) => (
   <div
      style={{
         fontSize: 10,
         fontWeight: 800,
         letterSpacing: "0.12em",
         color: T.indigo,
         textTransform: "uppercase",
         borderLeft: `3px solid ${T.indigo}`,
         paddingLeft: 8,
         marginBottom: 10,
         display: "flex",
         alignItems: "center",
         gap: 6,
      }}>
      {children}
   </div>
);

const Ann = ({ title, BoxIcon, items, color = T.indigo }) => (
   <div
      style={{
         background: "#fff",
         border: "1px solid #e5e7eb",
         borderTop: `3px solid ${color}`,
         borderRadius: 8,
         padding: "14px 16px",
         fontSize: 12,
         lineHeight: 1.7,
      }}>
      <div
         style={{
            fontWeight: 800,
            fontSize: 11,
            color,
            letterSpacing: "0.06em",
            marginBottom: 8,
            display: "flex",
            alignItems: "center",
            gap: 6,
         }}>
         {BoxIcon && (
            <BoxIcon
               size={12}
               strokeWidth={2.5}
            />
         )}
         {title}
      </div>
      <ul style={{ margin: 0, paddingLeft: 16, color: "#374151" }}>
         {items.map((it, i) => (
            <li key={i}>{it}</li>
         ))}
      </ul>
   </div>
);

// avatar look-up by key
const AV = {
   detective: { Icon: Eye, bg: "#fce7f3", color: "#be185d" },
   news: { Icon: Newspaper, bg: "#fef3c7", color: "#92400e" },
   politics: { Icon: Landmark, bg: "#dbeafe", color: "#1e40af" },
   satire: { Icon: Wand2, bg: "#ede9fe", color: T.violet },
   default: { Icon: User, bg: "#f3f4f6", color: T.gray },
};

// ─── View 1: Extension Popup ──────────────────────────────────────────────────
const ExtensionPopup = () => {
   const [tab, setTab] = useState("snip");
   const tabs = [
      { id: "snip", Icon: Scissors, label: "Snip" },
      { id: "upload", Icon: Upload, label: "Upload" },
      { id: "url", Icon: Link, label: "Scan URL" },
   ];
   return (
      <div
         style={{
            display: "grid",
            gridTemplateColumns: "340px 1fr",
            gap: 32,
            alignItems: "start",
         }}>
         <div>
            <SLabel>Extension Popup — 380×520px</SLabel>
            <div
               style={{
                  width: 340,
                  background: T.surface,
                  border: "1.5px solid #d1d5db",
                  borderRadius: 12,
                  overflow: "hidden",
                  boxShadow: "0 8px 32px rgba(0,0,0,0.12)",
               }}>
               {/* Header */}
               <div
                  style={{
                     background: T.indigo,
                     padding: "12px 16px",
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "space-between",
                  }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                     <Logo
                        size={14}
                        bg="rgba(255,255,255,0.2)"
                     />
                     <span style={{ color: "#fff", fontWeight: 800, fontSize: 14 }}>TruthLens</span>
                  </div>
                  <span
                     style={{
                        fontSize: 9,
                        color: "rgba(255,255,255,0.6)",
                        background: "rgba(255,255,255,0.12)",
                        padding: "2px 8px",
                        borderRadius: 999,
                     }}>
                     v1.0
                  </span>
               </div>
               {/* Tabs */}
               <div style={{ display: "flex", borderBottom: "1.5px solid #e5e7eb" }}>
                  {tabs.map(({ id, Icon: TI, label }) => (
                     <button
                        key={id}
                        onClick={() => setTab(id)}
                        style={{
                           flex: 1,
                           padding: "10px 4px",
                           fontSize: 11,
                           fontWeight: 700,
                           background: tab === id ? "#fff" : "#f9fafb",
                           color: tab === id ? T.indigo : T.gray,
                           border: "none",
                           borderBottom:
                              tab === id ? `2px solid ${T.indigo}` : "2px solid transparent",
                           cursor: "pointer",
                           display: "flex",
                           alignItems: "center",
                           justifyContent: "center",
                           gap: 5,
                        }}>
                        <TI
                           size={12}
                           strokeWidth={2.5}
                        />
                        {label}
                     </button>
                  ))}
               </div>
               {/* Panel */}
               <div style={{ padding: "20px 16px", minHeight: 180 }}>
                  {tab === "snip" && (
                     <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                        <div
                           style={{
                              background: "#eff6ff",
                              border: "2px dashed #bfdbfe",
                              borderRadius: 8,
                              padding: 20,
                              textAlign: "center",
                           }}>
                           <div
                              style={{
                                 display: "flex",
                                 justifyContent: "center",
                                 marginBottom: 8,
                              }}>
                              <div
                                 style={{
                                    width: 44,
                                    height: 44,
                                    background: "#dbeafe",
                                    borderRadius: 10,
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                 }}>
                                 <Crosshair
                                    size={22}
                                    color="#1d4ed8"
                                    strokeWidth={2}
                                 />
                              </div>
                           </div>
                           <div style={{ fontSize: 12, color: "#1d4ed8", fontWeight: 700 }}>
                              Activate Screen Snip
                           </div>
                           <div style={{ fontSize: 10, color: T.gray, marginTop: 4 }}>
                              Draw a box around the claim
                           </div>
                        </div>
                        <button
                           style={{
                              width: "100%",
                              background: T.indigo,
                              color: "#fff",
                              border: "none",
                              borderRadius: 8,
                              padding: "10px",
                              fontSize: 13,
                              fontWeight: 700,
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              gap: 8,
                           }}>
                           <Target
                              size={15}
                              strokeWidth={2.5}
                           />
                           Start Snipping
                        </button>
                     </div>
                  )}
                  {tab === "upload" && (
                     <div
                        style={{
                           background: "#f9fafb",
                           border: "2px dashed #d1d5db",
                           borderRadius: 8,
                           padding: 24,
                           textAlign: "center",
                        }}>
                        <div
                           style={{ display: "flex", justifyContent: "center", marginBottom: 10 }}>
                           <div
                              style={{
                                 width: 44,
                                 height: 44,
                                 background: "#f3f4f6",
                                 borderRadius: 10,
                                 display: "flex",
                                 alignItems: "center",
                                 justifyContent: "center",
                              }}>
                              <Upload
                                 size={22}
                                 color={T.gray}
                                 strokeWidth={1.8}
                              />
                           </div>
                        </div>
                        <div style={{ fontSize: 12, color: T.gray, fontWeight: 700 }}>
                           Drop image or PDF here
                        </div>
                        <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 4 }}>
                           or click to browse files
                        </div>
                        <button
                           style={{
                              marginTop: 12,
                              background: "#fff",
                              border: `1.5px solid ${T.indigo}`,
                              color: T.indigo,
                              borderRadius: 6,
                              padding: "6px 16px",
                              fontSize: 11,
                              fontWeight: 700,
                              cursor: "pointer",
                           }}>
                           Browse
                        </button>
                     </div>
                  )}
                  {tab === "url" && (
                     <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                        <div style={{ fontSize: 11, color: T.gray, fontWeight: 600 }}>
                           Paste article or claim URL
                        </div>
                        <div style={{ display: "flex", gap: 6 }}>
                           <div
                              style={{
                                 flex: 1,
                                 background: "#f9fafb",
                                 border: "1.5px solid #d1d5db",
                                 borderRadius: 6,
                                 padding: "8px 10px",
                                 fontSize: 11,
                                 color: "#9ca3af",
                                 display: "flex",
                                 alignItems: "center",
                                 gap: 6,
                              }}>
                              <Link
                                 size={11}
                                 color="#9ca3af"
                              />
                              https://example.com/article…
                           </div>
                           <button
                              style={{
                                 background: T.indigo,
                                 color: "#fff",
                                 border: "none",
                                 borderRadius: 6,
                                 padding: "8px 12px",
                                 fontSize: 11,
                                 fontWeight: 700,
                                 cursor: "pointer",
                                 display: "flex",
                                 alignItems: "center",
                                 gap: 5,
                              }}>
                              <ScanLine
                                 size={13}
                                 strokeWidth={2.5}
                              />
                              Scan
                           </button>
                        </div>
                        <div
                           style={{
                              background: "#f3f4f6",
                              borderRadius: 6,
                              padding: "8px 10px",
                              fontSize: 10,
                              color: T.gray,
                              display: "flex",
                              gap: 6,
                           }}>
                           <Lightbulb
                              size={12}
                              color={T.amber}
                              style={{ flexShrink: 0, marginTop: 1 }}
                           />
                           TruthLens will extract and analyze the main claims from this URL
                           automatically.
                        </div>
                     </div>
                  )}
               </div>
               {/* Footer */}
               <div
                  style={{
                     borderTop: "1.5px solid #f3f4f6",
                     padding: "10px 16px",
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "space-between",
                  }}>
                  <div
                     style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 5,
                        fontSize: 10,
                        color: T.gray,
                     }}>
                     <UserCircle
                        size={12}
                        color={T.gray}
                     />
                     Signed in as <strong>@user</strong>
                  </div>
                  <a
                     style={{
                        fontSize: 10,
                        color: T.indigo,
                        fontWeight: 700,
                        textDecoration: "none",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                     }}>
                     Open Web Dashboard
                     <ArrowRight size={10} />
                  </a>
               </div>
            </div>
         </div>
         <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Ann
               title="Visual Structure"
               BoxIcon={Ruler}
               color={T.indigo}
               items={[
                  "Fixed 380×520px container · border-radius: rounded-xl",
                  "Header → TabBar (3-col flex) → ActionArea (dynamic) → Footer",
                  "Tab indicator: border-b-2 border-indigo-600 on active tab",
                  "ActionArea uses conditional rendering, not hidden/show",
               ]}
            />
            <Ann
               title="React Components"
               BoxIcon={Braces}
               color="#7c3aed"
               items={[
                  "<ExtensionPopup> — root, manages `activeTab` state",
                  "<TabBar> — receives activeTab + setActiveTab as props",
                  "<SnipPanel> — contains CTA button, emits chrome.tabs message",
                  "<UploadPanel> — uses <FileDropZone> sub-component",
                  "<UrlScanPanel> — controlled input + submit handler",
                  "<ExtensionFooter> — static link to web dashboard",
               ]}
            />
            <Ann
               title="Tailwind / UX Advice"
               BoxIcon={Palette}
               color={T.green}
               items={[
                  "Header: bg-indigo-600 text-white · sticky top-0",
                  "Active tab: text-indigo-600 border-b-2 border-indigo-600 bg-white",
                  "Snip CTA: bg-indigo-600 hover:bg-indigo-700 · full width · py-2.5",
                  "Drop zone: border-2 border-dashed hover:border-indigo-400",
                  "Footer: text-xs text-gray-400 · border-t border-gray-100",
               ]}
            />
         </div>
      </div>
   );
};

// ─── View 2: Content Script Cards ────────────────────────────────────────────
const ContentCards = () => (
   <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32 }}>
      <div>
         <SLabel>Loading Card — Injected Overlay</SLabel>
         <div
            style={{
               background: T.surface,
               border: "1.5px solid #e5e7eb",
               borderRadius: 12,
               padding: 20,
               width: 300,
               boxShadow: "0 4px 24px rgba(0,0,0,0.1)",
            }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
               <div style={{ width: 8, height: 8, background: T.indigo, borderRadius: "50%" }} />
               <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Search
                     size={12}
                     color={T.indigo}
                     strokeWidth={2.5}
                  />
                  <span style={{ fontSize: 12, fontWeight: 700, color: T.indigo }}>TruthLens</span>
               </div>
               <X
                  size={13}
                  color={T.gray}
                  style={{ marginLeft: "auto", cursor: "pointer" }}
               />
            </div>
            <div
               style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexDirection: "column",
                  gap: 10,
                  padding: "16px 0",
               }}>
               <div
                  style={{
                     width: 36,
                     height: 36,
                     border: `3px solid #e5e7eb`,
                     borderTop: `3px solid ${T.indigo}`,
                     borderRadius: "50%",
                  }}
               />
               <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>
                  Analyzing claim…
               </span>
               <div style={{ width: "100%", background: "#f3f4f6", borderRadius: 999, height: 4 }}>
                  <div
                     style={{ width: "60%", background: T.indigo, borderRadius: 999, height: 4 }}
                  />
               </div>
               <span
                  style={{
                     fontSize: 10,
                     color: T.gray,
                     display: "flex",
                     alignItems: "center",
                     gap: 4,
                  }}>
                  <BookOpen
                     size={10}
                     color={T.gray}
                  />
                  Querying 3 fact-check databases
               </span>
            </div>
         </div>
         <div style={{ marginTop: 16 }}>
            <Ann
               title="Components"
               BoxIcon={Braces}
               color={T.indigo}
               items={[
                  "<AnalysisLoader> — portaled into DOM via content_script",
                  "Animated progress bar using CSS transition + React state",
                  "Draggable: use CSS cursor-grab on header drag handle",
                  "Close (X) button dispatches removeOverlay() action",
               ]}
            />
         </div>
      </div>
      <div>
         <SLabel>Result Card — Misleading State</SLabel>
         <div
            style={{
               background: T.surface,
               border: `1.5px solid ${T.amber}`,
               borderRadius: 12,
               overflow: "hidden",
               width: 320,
               boxShadow: "0 4px 24px rgba(0,0,0,0.12)",
            }}>
            <div
               style={{
                  background: T.amberBg,
                  borderBottom: `1.5px solid ${T.amber}`,
                  padding: "7px 14px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
               }}>
               <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Flag
                     size={12}
                     color="#78350f"
                     strokeWidth={2.5}
                  />
                  <span style={{ fontSize: 11, fontWeight: 800, color: "#78350f" }}>
                     CLAIM FLAGGED
                  </span>
               </div>
               <X
                  size={13}
                  color="#78350f"
                  style={{ cursor: "pointer" }}
               />
            </div>
            <div style={{ padding: 16 }}>
               <div
                  style={{
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "space-between",
                     marginBottom: 10,
                  }}>
                  <VerdictBadge verdict="misleading" />
                  <span style={{ fontSize: 10, color: T.gray }}>2s ago</span>
               </div>
               <div
                  style={{
                     background: "#f9fafb",
                     borderRadius: 6,
                     padding: "10px 12px",
                     marginBottom: 12,
                  }}>
                  <div
                     style={{
                        fontSize: 9,
                        fontWeight: 800,
                        color: T.gray,
                        letterSpacing: "0.08em",
                        marginBottom: 4,
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                     }}>
                     <Sparkles
                        size={9}
                        color={T.gray}
                     />
                     AI SUMMARY
                  </div>
                  <p style={{ fontSize: 11, color: "#374151", lineHeight: 1.6, margin: 0 }}>
                     This claim lacks sufficient context. The statistic cited is real, but omits a
                     5-year comparison window that reverses the implication.
                  </p>
               </div>
               <div style={{ marginBottom: 14 }}>
                  <div
                     style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                     <span
                        style={{
                           fontSize: 9,
                           fontWeight: 700,
                           color: T.gray,
                           letterSpacing: "0.06em",
                           display: "flex",
                           alignItems: "center",
                           gap: 4,
                        }}>
                        <BarChart2 size={9} />
                        AI CONFIDENCE
                     </span>
                     <span style={{ fontSize: 10, fontWeight: 800, color: T.amber }}>62%</span>
                  </div>
                  <div style={{ background: "#f3f4f6", borderRadius: 999, height: 6 }}>
                     <div
                        style={{
                           width: "62%",
                           background: `linear-gradient(90deg,${T.green},${T.amber})`,
                           borderRadius: 999,
                           height: 6,
                        }}
                     />
                  </div>
                  <div style={{ fontSize: 9, color: "#9ca3af", marginTop: 3 }}>
                     Low confidence — human review recommended
                  </div>
               </div>
               <button
                  style={{
                     width: "100%",
                     background: T.indigo,
                     color: "#fff",
                     border: "none",
                     borderRadius: 8,
                     padding: "9px",
                     fontSize: 12,
                     fontWeight: 700,
                     cursor: "pointer",
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "center",
                     gap: 7,
                  }}>
                  <Users
                     size={14}
                     strokeWidth={2.5}
                  />
                  Ask the Community?
               </button>
               <div style={{ textAlign: "center", marginTop: 8 }}>
                  <a
                     style={{
                        fontSize: 9,
                        color: T.gray,
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 4,
                     }}>
                     View full analysis in dashboard
                     <ExternalLink size={9} />
                  </a>
               </div>
            </div>
         </div>
         <div style={{ marginTop: 16 }}>
            <Ann
               title="UX / Tailwind Advice"
               BoxIcon={Palette}
               color={T.amber}
               items={[
                  "Strip + border color = verdict semantic color (dynamic)",
                  "For `verified`: green strip · For `fake`: red border · etc.",
                  "Confidence bar: gradient green→amber→red based on score",
                  "CTA 'Ask Community' only visible when verdict = unverified/misleading",
                  "Card enters via slide-in: translate-y-4 → translate-y-0, opacity-0 → 1",
               ]}
            />
         </div>
      </div>
   </div>
);

// ─── View 3: Auth Pages ───────────────────────────────────────────────────────
const AuthPages = () => {
   const [mode, setMode] = useState("login");
   return (
      <div
         style={{
            display: "grid",
            gridTemplateColumns: "420px 1fr",
            gap: 32,
            alignItems: "start",
         }}>
         <div>
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
               {["login", "register"].map((m) => (
                  <button
                     key={m}
                     onClick={() => setMode(m)}
                     style={{
                        padding: "5px 16px",
                        borderRadius: 999,
                        fontSize: 11,
                        fontWeight: 700,
                        cursor: "pointer",
                        background: mode === m ? T.indigo : "#f3f4f6",
                        color: mode === m ? "#fff" : T.gray,
                        border: "none",
                     }}>
                     {m === "login" ? "Login" : "Register"}
                  </button>
               ))}
            </div>
            <SLabel>{mode === "login" ? "Login Page" : "Register Page"}</SLabel>
            <div
               style={{
                  background: T.bg,
                  minHeight: 540,
                  borderRadius: 12,
                  border: "1.5px solid #e5e7eb",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: 24,
               }}>
               <div style={{ width: "100%", maxWidth: 360 }}>
                  <div style={{ textAlign: "center", marginBottom: 28 }}>
                     <div
                        style={{
                           display: "inline-flex",
                           alignItems: "center",
                           justifyContent: "center",
                           width: 52,
                           height: 52,
                           background: T.indigo,
                           borderRadius: 14,
                           marginBottom: 12,
                        }}>
                        <Search
                           size={24}
                           color="#fff"
                           strokeWidth={2.5}
                        />
                     </div>
                     <div
                        style={{
                           fontSize: 22,
                           fontWeight: 900,
                           color: "#111827",
                           letterSpacing: "-0.02em",
                        }}>
                        TruthLens
                     </div>
                     <div style={{ fontSize: 12, color: T.gray, marginTop: 2 }}>
                        {mode === "login" ? "Welcome back" : "Join the fact-checking community"}
                     </div>
                  </div>
                  {mode === "register" && (
                     <div
                        style={{
                           background: "#eff6ff",
                           border: "1.5px solid #bfdbfe",
                           borderRadius: 10,
                           padding: "12px 14px",
                           marginBottom: 20,
                        }}>
                        <div
                           style={{
                              fontSize: 11,
                              fontWeight: 800,
                              color: "#1d4ed8",
                              marginBottom: 6,
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                           }}>
                           <Trophy
                              size={13}
                              color="#1d4ed8"
                              strokeWidth={2.5}
                           />
                           Earn Your Trust Score
                        </div>
                        <p style={{ fontSize: 11, color: "#1e40af", lineHeight: 1.6, margin: 0 }}>
                           Vote on evidence, submit sources, and resolve debates. Your{" "}
                           <strong>Trust Score</strong> grows with every verified contribution —
                           unlocking higher voting weight.
                        </p>
                     </div>
                  )}
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                     {mode === "register" && (
                        <div>
                           <label
                              style={{
                                 fontSize: 11,
                                 fontWeight: 700,
                                 color: "#374151",
                                 display: "block",
                                 marginBottom: 4,
                              }}>
                              Username
                           </label>
                           <div
                              style={{
                                 background: "#fff",
                                 border: "1.5px solid #d1d5db",
                                 borderRadius: 7,
                                 padding: "9px 12px",
                                 fontSize: 12,
                                 color: "#9ca3af",
                                 display: "flex",
                                 gap: 7,
                                 alignItems: "center",
                              }}>
                              <User
                                 size={13}
                                 color="#9ca3af"
                              />
                              Choose a unique username…
                           </div>
                        </div>
                     )}
                     <div>
                        <label
                           style={{
                              fontSize: 11,
                              fontWeight: 700,
                              color: "#374151",
                              display: "block",
                              marginBottom: 4,
                           }}>
                           Email
                        </label>
                        <div
                           style={{
                              background: "#fff",
                              border: "1.5px solid #d1d5db",
                              borderRadius: 7,
                              padding: "9px 12px",
                              fontSize: 12,
                              color: "#9ca3af",
                              display: "flex",
                              gap: 7,
                              alignItems: "center",
                           }}>
                           <Layers
                              size={13}
                              color="#9ca3af"
                           />
                           you@example.com
                        </div>
                     </div>
                     <div>
                        <label
                           style={{
                              fontSize: 11,
                              fontWeight: 700,
                              color: "#374151",
                              display: "block",
                              marginBottom: 4,
                           }}>
                           Password
                        </label>
                        <div
                           style={{
                              background: "#fff",
                              border: "1.5px solid #d1d5db",
                              borderRadius: 7,
                              padding: "9px 12px",
                              fontSize: 12,
                              color: "#9ca3af",
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                           }}>
                           <div style={{ display: "flex", gap: 7, alignItems: "center" }}>
                              <Shield
                                 size={13}
                                 color="#9ca3af"
                              />
                              ••••••••••
                           </div>
                           <div
                              style={{
                                 display: "flex",
                                 alignItems: "center",
                                 gap: 4,
                                 fontSize: 10,
                                 color: T.indigo,
                                 cursor: "pointer",
                              }}>
                              <Eye
                                 size={11}
                                 color={T.indigo}
                              />
                              Show
                           </div>
                        </div>
                     </div>
                     {mode === "login" && (
                        <div style={{ textAlign: "right" }}>
                           <a
                              style={{
                                 fontSize: 10,
                                 color: T.indigo,
                                 cursor: "pointer",
                                 fontWeight: 600,
                              }}>
                              Forgot password?
                           </a>
                        </div>
                     )}
                     <button
                        style={{
                           background: T.indigo,
                           color: "#fff",
                           border: "none",
                           borderRadius: 8,
                           padding: "11px",
                           fontSize: 13,
                           fontWeight: 700,
                           cursor: "pointer",
                           marginTop: 4,
                           display: "flex",
                           alignItems: "center",
                           justifyContent: "center",
                           gap: 8,
                        }}>
                        {mode === "login" ? "Sign In" : "Create Account"}
                        <ArrowRight
                           size={15}
                           strokeWidth={2.5}
                        />
                     </button>
                  </div>
                  <div style={{ textAlign: "center", marginTop: 16, fontSize: 11, color: T.gray }}>
                     {mode === "login" ? (
                        <span>
                           No account?{" "}
                           <a
                              style={{ color: T.indigo, fontWeight: 700, cursor: "pointer" }}
                              onClick={() => setMode("register")}>
                              Register
                           </a>
                        </span>
                     ) : (
                        <span>
                           Already registered?{" "}
                           <a
                              style={{ color: T.indigo, fontWeight: 700, cursor: "pointer" }}
                              onClick={() => setMode("login")}>
                              Sign In
                           </a>
                        </span>
                     )}
                  </div>
               </div>
            </div>
         </div>
         <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Ann
               title="Visual Structure"
               BoxIcon={Ruler}
               color={T.indigo}
               items={[
                  "Full-viewport: min-h-screen bg-gray-50 flex items-center justify-center",
                  "Card: max-w-sm w-full bg-white rounded-2xl shadow-lg p-8",
                  "Logo → (ValueProp?) → Form fields → Submit → Toggle link",
                  "Value prop box: bg-blue-50 border border-blue-200 rounded-xl",
               ]}
            />
            <Ann
               title="React Components"
               BoxIcon={Braces}
               color="#7c3aed"
               items={[
                  "<AuthLayout> — centers card, sets bg-gray-50",
                  "<BrandLogo> — reusable icon + wordmark",
                  "<ValueProposition> — Register-only info card",
                  "<FormField> — reusable label + input + error state",
                  "<PasswordField> — extends FormField, show/hide toggle",
                  "<AuthForm> — form logic, validation, submit handler",
               ]}
            />
            <Ann
               title="UX / Tailwind Advice"
               BoxIcon={Palette}
               color={T.green}
               items={[
                  "Input focus: focus:ring-2 focus:ring-indigo-500",
                  "Error state: border-red-500 + text-red-600 helper text",
                  "Submit btn: w-full py-2.5 hover:bg-indigo-700 transition-colors",
                  "Value prop: text-blue-700 text-sm — acts as social proof",
                  "No decorative imagery — trust is conveyed through restraint",
               ]}
            />
         </div>
      </div>
   );
};

// ─── View 4: Personal Dashboard ───────────────────────────────────────────────
const PersonalDashboard = () => {
   const scans = [
      { Icon: Globe, text: '"5G towers cause cancer"', verdict: "fake", date: "Jun 12" },
      {
         Icon: Newspaper,
         text: '"Unemployment at 50-year low"',
         verdict: "verified",
         date: "Jun 11",
      },
      {
         Icon: MessageSquare,
         text: '"Coffee cures diabetes — study"',
         verdict: "misleading",
         date: "Jun 10",
      },
      { Icon: Image, text: '"Photo from 2018 shared as 2024"', verdict: "fake", date: "Jun 9" },
   ];
   const nav = [
      { Icon: LayoutDashboard, label: "Dashboard", active: true },
      { Icon: Globe, label: "Community Feed", active: false },
      { Icon: Settings, label: "Settings", active: false },
   ];
   return (
      <div
         style={{
            display: "grid",
            gridTemplateColumns: "200px 1fr",
            gap: 0,
            background: T.bg,
            borderRadius: 12,
            border: "1.5px solid #e5e7eb",
            overflow: "hidden",
            minHeight: 600,
         }}>
         {/* Sidebar */}
         <div
            style={{
               background: T.dark,
               padding: "24px 0",
               display: "flex",
               flexDirection: "column",
            }}>
            <div
               style={{ padding: "0 16px 20px", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
               <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Logo size={14} />
                  <span style={{ color: "#fff", fontWeight: 800, fontSize: 14 }}>TruthLens</span>
               </div>
            </div>
            <nav style={{ padding: "16px 8px", flex: 1 }}>
               {nav.map(({ Icon: NI, label, active }) => (
                  <div
                     key={label}
                     style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        padding: "9px 12px",
                        borderRadius: 8,
                        marginBottom: 2,
                        background: active ? "rgba(79,70,229,0.3)" : "transparent",
                        cursor: "pointer",
                     }}>
                     <NI
                        size={15}
                        color={active ? "#fff" : "rgba(255,255,255,0.45)"}
                        strokeWidth={active ? 2.5 : 2}
                     />
                     <span
                        style={{
                           fontSize: 12,
                           fontWeight: active ? 700 : 500,
                           color: active ? "#fff" : "rgba(255,255,255,0.55)",
                        }}>
                        {label}
                     </span>
                     {active && (
                        <div
                           style={{
                              width: 5,
                              height: 5,
                              background: T.indigo,
                              borderRadius: "50%",
                              marginLeft: "auto",
                           }}
                        />
                     )}
                  </div>
               ))}
            </nav>
            <div style={{ padding: "12px 16px", borderTop: "1px solid rgba(255,255,255,0.08)" }}>
               <Avatar
                  Icon={UserCircle}
                  bg="rgba(255,255,255,0.1)"
                  color="rgba(255,255,255,0.7)"
                  size={34}
               />
               <div style={{ fontSize: 11, fontWeight: 700, color: "#fff", marginTop: 6 }}>
                  @verifyme
               </div>
               <div style={{ fontSize: 9, color: "rgba(255,255,255,0.4)" }}>Member since 2024</div>
            </div>
         </div>
         {/* Main */}
         <div style={{ padding: 24 }}>
            {/* Profile */}
            <div
               style={{
                  background: "#fff",
                  borderRadius: 10,
                  padding: "20px 24px",
                  border: "1.5px solid #e5e7eb",
                  marginBottom: 20,
                  display: "flex",
                  alignItems: "center",
                  gap: 20,
               }}>
               <Avatar
                  Icon={UserCircle}
                  bg="#ddd6fe"
                  color={T.violet}
                  size={56}
               />
               <div style={{ flex: 1 }}>
                  <div
                     style={{
                        fontSize: 18,
                        fontWeight: 900,
                        color: "#111827",
                        letterSpacing: "-0.01em",
                     }}>
                     @verifyme
                  </div>
                  <div
                     style={{
                        fontSize: 12,
                        color: T.gray,
                        marginTop: 2,
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                     }}>
                     <BadgeCheck
                        size={12}
                        color={T.green}
                     />
                     Fact-checker · Joined June 2024
                  </div>
                  <div style={{ fontSize: 11, color: "#374151", marginTop: 4 }}>
                     Passionate about media literacy and combating misinformation online.
                  </div>
               </div>
               <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                  <TrustGauge score={82} />
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                     <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 18, fontWeight: 900, color: "#111827" }}>47</div>
                        <div
                           style={{
                              fontSize: 9,
                              color: T.gray,
                              letterSpacing: "0.06em",
                              display: "flex",
                              alignItems: "center",
                              gap: 3,
                              justifyContent: "center",
                           }}>
                           <ScanLine size={8} />
                           SCANS
                        </div>
                     </div>
                     <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 18, fontWeight: 900, color: "#111827" }}>23</div>
                        <div
                           style={{
                              fontSize: 9,
                              color: T.gray,
                              letterSpacing: "0.06em",
                              display: "flex",
                              alignItems: "center",
                              gap: 3,
                              justifyContent: "center",
                           }}>
                           <ThumbsUp size={8} />
                           VOTES
                        </div>
                     </div>
                  </div>
               </div>
            </div>
            {/* Scans table */}
            <SLabel>My Scans</SLabel>
            <div
               style={{
                  background: "#fff",
                  borderRadius: 10,
                  border: "1.5px solid #e5e7eb",
                  overflow: "hidden",
                  marginBottom: 20,
               }}>
               <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                     <tr style={{ background: "#f9fafb", borderBottom: "1.5px solid #e5e7eb" }}>
                        {["", "Claim Excerpt", "AI Verdict", "Date", "Actions"].map((h) => (
                           <th
                              key={h}
                              style={{
                                 textAlign: "left",
                                 padding: "10px 14px",
                                 fontSize: 10,
                                 fontWeight: 800,
                                 color: T.gray,
                                 letterSpacing: "0.06em",
                              }}>
                              {h}
                           </th>
                        ))}
                     </tr>
                  </thead>
                  <tbody>
                     {scans.map((c, i) => (
                        <tr
                           key={i}
                           style={{ borderBottom: "1px solid #f3f4f6" }}>
                           <td style={{ padding: "10px 14px" }}>
                              <div
                                 style={{
                                    width: 32,
                                    height: 32,
                                    background: "#f3f4f6",
                                    borderRadius: 6,
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                 }}>
                                 <c.Icon
                                    size={15}
                                    color={T.gray}
                                    strokeWidth={1.8}
                                 />
                              </div>
                           </td>
                           <td
                              style={{
                                 padding: "10px 14px",
                                 fontSize: 12,
                                 color: "#374151",
                                 maxWidth: 200,
                              }}>
                              {c.text}
                           </td>
                           <td style={{ padding: "10px 14px" }}>
                              <VerdictBadge verdict={c.verdict} />
                           </td>
                           <td style={{ padding: "10px 14px", fontSize: 11, color: T.gray }}>
                              {c.date}
                           </td>
                           <td style={{ padding: "10px 14px" }}>
                              <div style={{ display: "flex", gap: 6 }}>
                                 <button
                                    style={{
                                       fontSize: 10,
                                       color: T.indigo,
                                       background: "#eff6ff",
                                       border: "none",
                                       borderRadius: 4,
                                       padding: "3px 8px",
                                       cursor: "pointer",
                                       fontWeight: 600,
                                       display: "flex",
                                       alignItems: "center",
                                       gap: 4,
                                    }}>
                                    <Eye
                                       size={10}
                                       color={T.indigo}
                                    />
                                    View
                                 </button>
                                 <button
                                    style={{
                                       fontSize: 10,
                                       color: T.gray,
                                       background: "#f3f4f6",
                                       border: "none",
                                       borderRadius: 4,
                                       padding: "3px 8px",
                                       cursor: "pointer",
                                       display: "flex",
                                       alignItems: "center",
                                       gap: 4,
                                    }}>
                                    <ExternalLink
                                       size={10}
                                       color={T.gray}
                                    />
                                    Share
                                 </button>
                              </div>
                           </td>
                        </tr>
                     ))}
                  </tbody>
               </table>
            </div>
            {/* Contributions */}
            <SLabel>My Contributions</SLabel>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
               {[
                  {
                     Icon: MessageCircle,
                     type: "Thread",
                     title: "Viral vaccine efficacy chart debunked?",
                     status: "unverified",
                     votes: 12,
                  },
                  {
                     Icon: Paperclip,
                     type: "Evidence",
                     title: "CDC report linked to 5G debate",
                     status: "verified",
                     votes: 8,
                  },
               ].map((c, i) => (
                  <div
                     key={i}
                     style={{
                        background: "#fff",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 8,
                        padding: "12px 14px",
                     }}>
                     <div
                        style={{
                           display: "flex",
                           justifyContent: "space-between",
                           marginBottom: 6,
                        }}>
                        <span
                           style={{
                              fontSize: 9,
                              fontWeight: 800,
                              color: T.indigo,
                              letterSpacing: "0.08em",
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                           }}>
                           <c.Icon
                              size={9}
                              color={T.indigo}
                           />
                           {c.type.toUpperCase()}
                        </span>
                        <VerdictBadge verdict={c.status} />
                     </div>
                     <div
                        style={{
                           fontSize: 12,
                           fontWeight: 600,
                           color: "#111827",
                           marginBottom: 4,
                        }}>
                        {c.title}
                     </div>
                     <div
                        style={{
                           fontSize: 10,
                           color: T.gray,
                           display: "flex",
                           alignItems: "center",
                           gap: 4,
                        }}>
                        <ThumbsUp
                           size={10}
                           color={T.gray}
                        />
                        {c.votes} upvotes received
                     </div>
                  </div>
               ))}
            </div>
         </div>
      </div>
   );
};

// ─── Shared Post Card ─────────────────────────────────────────────────────────
const PostCard = ({ post, onClick }) => {
   const borderColor =
      { verified: T.green, fake: T.red, misleading: T.amber, unverified: T.gray, satire: T.violet }[
         post.verdict
      ] || T.gray;
   const av = AV[post.avatarKey] || AV.default;
   return (
      <div
         onClick={onClick}
         style={{
            background: "#fff",
            border: "1.5px solid #e5e7eb",
            borderRadius: 14,
            overflow: "hidden",
            boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
            cursor: onClick ? "pointer" : "default",
         }}>
         {/* Header */}
         <div
            style={{
               padding: "14px 16px 10px",
               display: "flex",
               alignItems: "center",
               justifyContent: "space-between",
            }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
               <Avatar
                  Icon={av.Icon}
                  bg={av.bg}
                  color={av.color}
                  size={38}
               />
               <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#111827" }}>
                     {post.author}
                  </div>
                  <div
                     style={{
                        fontSize: 10,
                        color: T.gray,
                        marginTop: 1,
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                     }}>
                     {post.date}
                     <span style={{ color: "#d1d5db" }}>·</span>
                     <Search
                        size={9}
                        color={T.indigo}
                     />
                     <span style={{ color: T.indigo, fontWeight: 600 }}>via TruthLens</span>
                  </div>
               </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
               <VerdictBadge verdict={post.verdict} />
               <MoreHorizontal
                  size={18}
                  color="#9ca3af"
                  style={{ cursor: "pointer" }}
               />
            </div>
         </div>
         {/* Caption */}
         <div style={{ padding: "0 16px 10px" }}>
            <p style={{ fontSize: 13, color: "#1f2937", lineHeight: 1.6, margin: 0 }}>
               <span style={{ fontWeight: 700 }}>Flagged claim: </span>
               {post.caption}
            </p>
         </div>
         {/* Image */}
         <div
            style={{
               position: "relative",
               borderTop: "1.5px solid #f0f0f0",
               borderBottom: "1.5px solid #f0f0f0",
            }}>
            <ImgPlaceholder
               label={`Snipped from ${post.source}`}
               Icon={post.imageIcon || Image}
            />
            <div
               style={{
                  position: "absolute",
                  bottom: 0,
                  left: 0,
                  right: 0,
                  background: `${borderColor}18`,
                  borderTop: `3px solid ${borderColor}`,
                  padding: "6px 12px",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
               }}>
               <VerdictBadge verdict={post.verdict} />
               <span style={{ fontSize: 10, color: "#374151", fontWeight: 600 }}>
                  AI Confidence: <strong>{post.confidence}%</strong>
               </span>
               <span
                  style={{
                     marginLeft: "auto",
                     fontSize: 10,
                     background: "#fff",
                     color: T.gray,
                     borderRadius: 4,
                     padding: "2px 7px",
                     fontWeight: 600,
                     border: "1px solid #e5e7eb",
                  }}>
                  {post.status}
               </span>
            </div>
         </div>
         {/* Reactions */}
         <div
            style={{
               padding: "10px 16px",
               display: "flex",
               alignItems: "center",
               gap: 4,
               borderBottom: "1px solid #f3f4f6",
            }}>
            <div style={{ display: "flex", gap: 2 }}>
               {[ThumbsUp, Star, HelpCircle].map((RI, i) => (
                  <span
                     key={i}
                     style={{
                        width: 22,
                        height: 22,
                        background: "#f3f4f6",
                        borderRadius: "50%",
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                     }}>
                     <RI
                        size={11}
                        color={T.gray}
                        strokeWidth={1.8}
                     />
                  </span>
               ))}
            </div>
            <span style={{ fontSize: 11, color: T.gray, marginLeft: 6 }}>
               {post.reactions} reactions
            </span>
            <span
               style={{
                  marginLeft: "auto",
                  fontSize: 11,
                  color: T.gray,
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
               }}>
               <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
                  <MessageCircle
                     size={11}
                     color={T.gray}
                  />
                  {post.comments}
               </span>
               <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
                  <Paperclip
                     size={11}
                     color={T.gray}
                  />
                  {post.evidence} evidence
               </span>
            </span>
         </div>
         {/* Actions */}
         <div style={{ padding: "4px 8px", display: "flex" }}>
            {[
               { Icon: ThumbsUp, label: "React", color: "#374151" },
               { Icon: MessageCircle, label: "Comment", color: "#374151" },
               { Icon: Paperclip, label: "Add Evidence", color: T.indigo },
            ].map(({ Icon: AI, label, color }) => (
               <button
                  key={label}
                  style={{
                     flex: 1,
                     padding: "8px 4px",
                     background: "transparent",
                     border: "none",
                     fontSize: 12,
                     fontWeight: 600,
                     color,
                     cursor: "pointer",
                     borderRadius: 6,
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "center",
                     gap: 6,
                  }}>
                  <AI
                     size={14}
                     strokeWidth={2}
                  />
                  {label}
               </button>
            ))}
         </div>
      </div>
   );
};

// ─── View 5: Community Feed ───────────────────────────────────────────────────
const CommunityFeed = () => {
   const [activeFilter, setActiveFilter] = useState("trending");
   const posts = [
      {
         id: 1,
         verdict: "fake",
         avatarKey: "detective",
         author: "@photocheck",
         date: "2h ago",
         source: "Twitter / X",
         imageIcon: Globe,
         caption:
            '"Shocking aerial photo shows the aftermath of the 2024 flooding in Valencia, Spain."',
         confidence: 94,
         reactions: 142,
         comments: 89,
         evidence: 15,
         status: "Resolved",
      },
      {
         id: 2,
         verdict: "misleading",
         avatarKey: "news",
         author: "@skepticwatch",
         date: "5h ago",
         source: "Facebook",
         imageIcon: FileText,
         caption:
            '"New peer-reviewed study proves masks are completely ineffective against airborne COVID variants."',
         confidence: 62,
         reactions: 78,
         comments: 34,
         evidence: 7,
         status: "Needs Evidence",
      },
      {
         id: 3,
         verdict: "unverified",
         avatarKey: "politics",
         author: "@poliscan",
         date: "1d ago",
         source: "News Article",
         imageIcon: Landmark,
         caption:
            '"Senator has voted against the national healthcare bill on three separate occasions this term."',
         confidence: 41,
         reactions: 23,
         comments: 12,
         evidence: 3,
         status: "Pending",
      },
      {
         id: 4,
         verdict: "satire",
         avatarKey: "satire",
         author: "@theonion_watch",
         date: "3h ago",
         source: "Facebook Share",
         imageIcon: Sparkles,
         caption:
            '"Scientists Discover New Planet Composed Entirely Of Student Loan Debt" — shared without satire label as breaking news.',
         confidence: 99,
         reactions: 312,
         comments: 57,
         evidence: 4,
         status: "Resolved",
      },
   ];
   const filters = [
      { id: "trending", Icon: TrendingUp, label: "Trending" },
      { id: "verified", Icon: CheckCircle2, label: "Recently Verified" },
      { id: "needs", Icon: Search, label: "Needs Evidence" },
   ];
   return (
      <div
         style={{
            display: "grid",
            gridTemplateColumns: "520px 1fr",
            gap: 32,
            alignItems: "start",
         }}>
         <div>
            <SLabel>Community Feed — Facebook-style Layout</SLabel>
            {/* Filter bar */}
            <div
               style={{
                  background: "#fff",
                  border: "1.5px solid #e5e7eb",
                  borderRadius: 12,
                  padding: "12px 16px",
                  marginBottom: 16,
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  flexWrap: "wrap",
               }}>
               <span style={{ fontSize: 11, fontWeight: 800, color: T.gray, marginRight: 4 }}>
                  Filter:
               </span>
               {filters.map(({ id, Icon: FI, label }) => (
                  <button
                     key={id}
                     onClick={() => setActiveFilter(id)}
                     style={{
                        padding: "5px 12px",
                        borderRadius: 999,
                        fontSize: 11,
                        fontWeight: 700,
                        border: "none",
                        cursor: "pointer",
                        background: activeFilter === id ? T.indigo : "#f3f4f6",
                        color: activeFilter === id ? "#fff" : T.gray,
                        display: "flex",
                        alignItems: "center",
                        gap: 5,
                        transition: "all 0.15s",
                     }}>
                     <FI
                        size={11}
                        strokeWidth={2.5}
                     />
                     {label}
                  </button>
               ))}
               <div
                  style={{
                     marginLeft: "auto",
                     background: "#f9fafb",
                     border: "1.5px solid #e5e7eb",
                     borderRadius: 8,
                     padding: "6px 12px",
                     fontSize: 11,
                     color: "#9ca3af",
                     display: "flex",
                     alignItems: "center",
                     gap: 6,
                  }}>
                  <Search
                     size={12}
                     color="#9ca3af"
                  />
                  Search claims…
               </div>
            </div>
            {/* Create prompt */}
            <div
               style={{
                  background: "#fff",
                  border: "1.5px solid #e5e7eb",
                  borderRadius: 12,
                  padding: "12px 16px",
                  marginBottom: 16,
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
               }}>
               <Avatar
                  Icon={UserCircle}
                  bg="#ede9fe"
                  color={T.violet}
                  size={36}
               />
               <div
                  style={{
                     flex: 1,
                     background: "#f9fafb",
                     border: "1.5px solid #e5e7eb",
                     borderRadius: 999,
                     padding: "9px 16px",
                     fontSize: 12,
                     color: "#9ca3af",
                     cursor: "pointer",
                  }}>
                  Flag a new claim for the community…
               </div>
               <button
                  style={{
                     background: T.indigo,
                     color: "#fff",
                     border: "none",
                     borderRadius: 8,
                     padding: "8px 14px",
                     fontSize: 11,
                     fontWeight: 700,
                     cursor: "pointer",
                     flexShrink: 0,
                     display: "flex",
                     alignItems: "center",
                     gap: 6,
                  }}>
                  <Scissors
                     size={13}
                     strokeWidth={2.5}
                  />
                  Snip
               </button>
            </div>
            {/* Posts */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
               {posts.map((p) => (
                  <PostCard
                     key={p.id}
                     post={p}
                     onClick={() => {}}
                  />
               ))}
            </div>
         </div>
         <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Ann
               title="Visual Structure"
               BoxIcon={Ruler}
               color={T.indigo}
               items={[
                  "Centered single column, max-w-xl · FilterBar → CreatePrompt → PostCards",
                  "PostCard: Header → Caption → SnippedImage → VerdictOverlay → Reactions → Actions",
                  "Verdict overlay strip: absolute bottom of image, border-t-4 semantic color",
                  "ActionRow: React · Comment · Add Evidence (3 equal-width flex buttons)",
               ]}
            />
            <Ann
               title="React Components"
               BoxIcon={Braces}
               color="#7c3aed"
               items={[
                  "<CommunityFeed> — filter state, paginated post list",
                  "<FilterBar> — activeFilter pill state, onFilterChange prop",
                  "<CreatePostPrompt> — opens snip flow or upload modal",
                  "<PostCard> — full post unit, receives post object",
                  "<PostHeader> — Avatar, author, date, VerdictBadge, MoreHorizontal menu",
                  "<SnippedImageBlock> — ImgPlaceholder + VerdictOverlay",
                  "<ReactionBar> — icon stack + counts",
                  "<PostActionRow> — 3 action buttons",
               ]}
            />
            <Ann
               title="Tailwind / UX Advice"
               BoxIcon={Palette}
               color={T.green}
               items={[
                  "PostCard: rounded-2xl shadow-sm hover:shadow-md transition-shadow",
                  "Image: aspect-video or min-h-[200px] bg-gray-100",
                  "VerdictOverlay: absolute bottom-0 inset-x-0 bg-[verdict]/10 border-t-4",
                  "'Add Evidence': text-indigo-600 font-bold — distinct from other action btns",
                  "Infinite scroll: IntersectionObserver on last card sentinel",
               ]}
            />
            <Ann
               title="UX Patterns"
               BoxIcon={Puzzle}
               color={T.amber}
               items={[
                  "Click image → opens Thread Detail page",
                  "Click 'Comment' → expands inline input below ActionRow",
                  "Click 'Add Evidence' → Thread Detail, auto-opens Evidence form",
                  "MoreHorizontal menu → Report / Share / Copy Link",
                  "Verdict overlay: informational only, non-interactive in feed",
               ]}
            />
         </div>
      </div>
   );
};

// ─── View 6: Thread Detail ────────────────────────────────────────────────────
const ThreadDetail = () => {
   const [activeTab, setActiveTab] = useState("comments");
   const [showForm, setShowForm] = useState(false);
   const post = {
      id: 1,
      verdict: "misleading",
      avatarKey: "detective",
      author: "@photocheck",
      date: "2h ago",
      source: "Twitter / X",
      imageIcon: Globe,
      caption:
         '"Shocking aerial photo shows the aftermath of the 2024 flooding in Valencia, Spain."',
      confidence: 62,
      reactions: 142,
      comments: 89,
      evidence: 15,
      status: "Needs Evidence",
   };
   const evidence = [
      {
         user: "@factchecker_pro",
         score: 91,
         source: "reuters.com/article/…",
         expl: "Reuters fact-check from Jan 2024 directly contradicts this — the photo originates from a 2019 flood event in Southeast Asia, confirmed via reverse image search metadata.",
         up: 24,
         down: 3,
      },
      {
         user: "@mediawatcher",
         score: 67,
         source: "snopes.com/fact-check/…",
         expl: "Snopes has rated this image 'False' — the EXIF data and geotag place the photo origin 8,000 miles from Spain.",
         up: 17,
         down: 1,
      },
      {
         user: "@newbie_user",
         score: 22,
         source: "reddit.com/r/…",
         expl: "Found a thread discussing this photo on a local news subreddit.",
         up: 2,
         down: 8,
      },
   ];
   const comments = [
      {
         u: "@curious_cat",
         ak: "news",
         t: "Does the Trust Score of the submitter affect which evidence appears first in the board?",
         ts: "1h ago",
         likes: 5,
      },
      {
         u: "@moderator",
         ak: "politics",
         t: "Yes — higher Trust Score = higher weighted sort position. Evidence from score >80 floats to the top automatically.",
         ts: "45m ago",
         likes: 12,
         isMod: true,
      },
      {
         u: "@verifyme",
         ak: "detective",
         t: "I've seen this photo used at least 3 times in different contexts this year alone. The metadata is the smoking gun.",
         ts: "30m ago",
         likes: 8,
      },
   ];
   const tier = (s) => (s >= 75 ? T.green : s >= 45 ? T.amber : T.red);
   return (
      <div style={{ maxWidth: 600 }}>
         <SLabel>Thread Detail — Full Post + Tabbed Engagement</SLabel>
         <PostCard post={post} />
         {/* Evidence Toggle */}
         <div style={{ marginTop: 12 }}>
            <button
               onClick={() => setShowForm((v) => !v)}
               style={{
                  width: "100%",
                  background: showForm ? "#eff6ff" : T.indigo,
                  color: showForm ? T.indigo : "#fff",
                  border: `1.5px solid ${showForm ? T.indigo : "transparent"}`,
                  borderRadius: showForm ? "10px 10px 0 0" : "10px",
                  padding: "11px",
                  fontSize: 13,
                  fontWeight: 700,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                  transition: "all 0.2s",
               }}>
               {showForm ? (
                  <>
                     <X
                        size={15}
                        strokeWidth={2.5}
                     />
                     Cancel Evidence Submission
                  </>
               ) : (
                  <>
                     <Paperclip
                        size={15}
                        strokeWidth={2.5}
                     />
                     Submit Evidence for This Claim
                  </>
               )}
            </button>
            {showForm && (
               <div
                  style={{
                     background: "#fff",
                     border: `1.5px solid ${T.indigo}`,
                     borderTop: "none",
                     borderRadius: "0 0 12px 12px",
                     padding: "20px 20px 16px",
                     boxShadow: "0 4px 16px rgba(79,70,229,0.08)",
                  }}>
                  <div
                     style={{
                        fontSize: 12,
                        fontWeight: 800,
                        color: T.indigo,
                        marginBottom: 14,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                     }}>
                     <Paperclip
                        size={13}
                        color={T.indigo}
                        strokeWidth={2.5}
                     />
                     New Evidence Submission
                  </div>
                  <div
                     style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: 12,
                        marginBottom: 12,
                     }}>
                     <div>
                        <label
                           style={{
                              fontSize: 11,
                              fontWeight: 700,
                              color: "#374151",
                              display: "block",
                              marginBottom: 4,
                           }}>
                           Source URL *
                        </label>
                        <div
                           style={{
                              background: "#f9fafb",
                              border: "1.5px solid #d1d5db",
                              borderRadius: 7,
                              padding: "9px 12px",
                              fontSize: 11,
                              color: "#9ca3af",
                              display: "flex",
                              gap: 6,
                              alignItems: "center",
                           }}>
                           <Link
                              size={11}
                              color="#9ca3af"
                           />
                           https://reliable-source.com/…
                        </div>
                     </div>
                     <div>
                        <label
                           style={{
                              fontSize: 11,
                              fontWeight: 700,
                              color: "#374151",
                              display: "block",
                              marginBottom: 4,
                           }}>
                           Evidence Type
                        </label>
                        <div
                           style={{
                              background: "#f9fafb",
                              border: "1.5px solid #d1d5db",
                              borderRadius: 7,
                              padding: "9px 12px",
                              fontSize: 11,
                              color: "#374151",
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                           }}>
                           <span>Contradicts Claim</span>
                           <ChevronDown
                              size={13}
                              color={T.gray}
                           />
                        </div>
                     </div>
                  </div>
                  <div style={{ marginBottom: 14 }}>
                     <label
                        style={{
                           fontSize: 11,
                           fontWeight: 700,
                           color: "#374151",
                           display: "block",
                           marginBottom: 4,
                        }}>
                        Explanation *
                     </label>
                     <div
                        style={{
                           background: "#f9fafb",
                           border: "1.5px solid #d1d5db",
                           borderRadius: 7,
                           padding: "10px 12px",
                           fontSize: 11,
                           color: "#9ca3af",
                           minHeight: 72,
                        }}>
                        Explain why this source supports or refutes the claim…
                     </div>
                  </div>
                  <div
                     style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                     }}>
                     <span
                        style={{
                           fontSize: 10,
                           color: T.gray,
                           display: "flex",
                           alignItems: "center",
                           gap: 4,
                        }}>
                        <BarChart2
                           size={11}
                           color={T.gray}
                        />
                        Your weight: <strong style={{ color: T.green }}>×1.8</strong> (Trust Score
                        82)
                     </span>
                     <div style={{ display: "flex", gap: 8 }}>
                        <button
                           onClick={() => setShowForm(false)}
                           style={{
                              background: "#f3f4f6",
                              color: T.gray,
                              border: "none",
                              borderRadius: 8,
                              padding: "8px 16px",
                              fontSize: 12,
                              fontWeight: 600,
                              cursor: "pointer",
                           }}>
                           Cancel
                        </button>
                        <button
                           style={{
                              background: T.indigo,
                              color: "#fff",
                              border: "none",
                              borderRadius: 8,
                              padding: "8px 20px",
                              fontSize: 12,
                              fontWeight: 700,
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                           }}>
                           Submit
                           <ArrowRight
                              size={13}
                              strokeWidth={2.5}
                           />
                        </button>
                     </div>
                  </div>
               </div>
            )}
         </div>
         {/* Tabbed section */}
         <div
            style={{
               background: "#fff",
               border: "1.5px solid #e5e7eb",
               borderRadius: 14,
               overflow: "hidden",
               marginTop: 12,
            }}>
            <div style={{ display: "flex", borderBottom: "1.5px solid #e5e7eb" }}>
               {[
                  { id: "comments", Icon: MessageCircle, label: `Comments (${post.comments})` },
                  { id: "evidence", Icon: Paperclip, label: `Evidence Board (${post.evidence})` },
               ].map(({ id, Icon: TI, label }) => (
                  <button
                     key={id}
                     onClick={() => setActiveTab(id)}
                     style={{
                        flex: 1,
                        padding: "13px 8px",
                        fontSize: 12,
                        fontWeight: 700,
                        background: activeTab === id ? "#fff" : "#f9fafb",
                        color: activeTab === id ? T.indigo : T.gray,
                        border: "none",
                        borderBottom:
                           activeTab === id ? `2px solid ${T.indigo}` : "2px solid transparent",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 7,
                        transition: "all 0.15s",
                     }}>
                     <TI
                        size={13}
                        strokeWidth={2.5}
                     />
                     {label}
                  </button>
               ))}
            </div>
            {/* Comments */}
            {activeTab === "comments" && (
               <div style={{ padding: 16 }}>
                  <div style={{ display: "flex", gap: 10, marginBottom: 18 }}>
                     <Avatar
                        Icon={UserCircle}
                        bg="#ede9fe"
                        color={T.violet}
                        size={32}
                     />
                     <div
                        style={{
                           flex: 1,
                           background: "#f9fafb",
                           border: "1.5px solid #e5e7eb",
                           borderRadius: 20,
                           padding: "9px 16px",
                           fontSize: 12,
                           color: "#9ca3af",
                           cursor: "text",
                           display: "flex",
                           alignItems: "center",
                           gap: 6,
                        }}>
                        <MessageSquare
                           size={13}
                           color="#9ca3af"
                        />
                        Write a comment…
                     </div>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                     {comments.map((c, i) => {
                        const av = AV[c.ak] || AV.default;
                        return (
                           <div
                              key={i}
                              style={{ display: "flex", gap: 10 }}>
                              <Avatar
                                 Icon={av.Icon}
                                 bg={c.isMod ? "#d1fae5" : av.bg}
                                 color={c.isMod ? T.green : av.color}
                                 size={32}
                              />
                              <div style={{ flex: 1 }}>
                                 <div
                                    style={{
                                       background: "#f9fafb",
                                       borderRadius: "0 12px 12px 12px",
                                       padding: "10px 14px",
                                    }}>
                                    <div
                                       style={{
                                          display: "flex",
                                          alignItems: "center",
                                          gap: 6,
                                          marginBottom: 4,
                                       }}>
                                       <span
                                          style={{
                                             fontSize: 12,
                                             fontWeight: 700,
                                             color: T.indigo,
                                          }}>
                                          {c.u}
                                       </span>
                                       {c.isMod && (
                                          <span
                                             style={{
                                                fontSize: 9,
                                                background: "#d1fae5",
                                                color: "#065f46",
                                                borderRadius: 4,
                                                padding: "1px 5px",
                                                fontWeight: 700,
                                                display: "flex",
                                                alignItems: "center",
                                                gap: 3,
                                             }}>
                                             <Shield
                                                size={8}
                                                strokeWidth={2.5}
                                             />
                                             MOD
                                          </span>
                                       )}
                                       <span
                                          style={{
                                             fontSize: 10,
                                             color: T.gray,
                                             marginLeft: "auto",
                                          }}>
                                          {c.ts}
                                       </span>
                                    </div>
                                    <p
                                       style={{
                                          fontSize: 12,
                                          color: "#374151",
                                          margin: 0,
                                          lineHeight: 1.6,
                                       }}>
                                       {c.t}
                                    </p>
                                 </div>
                                 <div
                                    style={{
                                       display: "flex",
                                       gap: 12,
                                       marginTop: 5,
                                       paddingLeft: 14,
                                    }}>
                                    <button
                                       style={{
                                          fontSize: 10,
                                          color: T.gray,
                                          background: "none",
                                          border: "none",
                                          cursor: "pointer",
                                          fontWeight: 600,
                                          display: "flex",
                                          alignItems: "center",
                                          gap: 4,
                                       }}>
                                       <ThumbsUp
                                          size={11}
                                          color={T.gray}
                                          strokeWidth={2}
                                       />
                                       {c.likes}
                                    </button>
                                    <button
                                       style={{
                                          fontSize: 10,
                                          color: T.gray,
                                          background: "none",
                                          border: "none",
                                          cursor: "pointer",
                                          fontWeight: 600,
                                       }}>
                                       Reply
                                    </button>
                                 </div>
                              </div>
                           </div>
                        );
                     })}
                  </div>
               </div>
            )}
            {/* Evidence board */}
            {activeTab === "evidence" && (
               <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
                  <div
                     style={{
                        fontSize: 11,
                        color: T.gray,
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                     }}>
                     <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <BarChart2
                           size={12}
                           color={T.gray}
                        />
                        Sorted by weighted trust score
                     </span>
                     <span
                        style={{
                           fontSize: 10,
                           background: "#f3f4f6",
                           borderRadius: 4,
                           padding: "2px 8px",
                        }}>
                        weighted = (up × trust/100) − (down × 0.5)
                     </span>
                  </div>
                  {evidence.map((e, i) => (
                     <div
                        key={i}
                        style={{
                           background: "#fff",
                           border: "1.5px solid #e5e7eb",
                           borderLeft: `4px solid ${tier(e.score)}`,
                           borderRadius: 10,
                           padding: "14px 16px",
                        }}>
                        <div
                           style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              marginBottom: 8,
                           }}>
                           <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <Avatar
                                 Icon={UserCircle}
                                 bg="#ede9fe"
                                 color={T.violet}
                                 size={28}
                              />
                              <div>
                                 <div style={{ fontSize: 12, fontWeight: 700, color: "#111827" }}>
                                    {e.user}
                                 </div>
                                 <div
                                    style={{
                                       fontSize: 9,
                                       color: T.gray,
                                       display: "flex",
                                       alignItems: "center",
                                       gap: 3,
                                    }}>
                                    <BadgeCheck
                                       size={9}
                                       color={tier(e.score)}
                                    />
                                    Trust:{" "}
                                    <strong style={{ color: tier(e.score) }}>{e.score}</strong>
                                 </div>
                              </div>
                           </div>
                           <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              {i === 0 && (
                                 <span
                                    style={{
                                       fontSize: 9,
                                       background: "#d1fae5",
                                       color: "#065f46",
                                       borderRadius: 4,
                                       padding: "2px 6px",
                                       fontWeight: 700,
                                       display: "flex",
                                       alignItems: "center",
                                       gap: 3,
                                    }}>
                                    <Star
                                       size={8}
                                       strokeWidth={2.5}
                                    />
                                    Top
                                 </span>
                              )}
                              <a
                                 style={{
                                    fontSize: 10,
                                    color: T.indigo,
                                    fontWeight: 600,
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 3,
                                 }}>
                                 <ExternalLink
                                    size={10}
                                    color={T.indigo}
                                 />
                                 {e.source}
                              </a>
                           </div>
                        </div>
                        <p
                           style={{
                              fontSize: 12,
                              color: "#374151",
                              lineHeight: 1.6,
                              margin: "0 0 10px",
                           }}>
                           {e.expl}
                        </p>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                           <button
                              style={{
                                 display: "flex",
                                 alignItems: "center",
                                 gap: 5,
                                 background: "#f0fdf4",
                                 border: "1.5px solid #bbf7d0",
                                 borderRadius: 6,
                                 padding: "4px 10px",
                                 cursor: "pointer",
                                 fontSize: 11,
                                 fontWeight: 700,
                                 color: "#166534",
                              }}>
                              <ChevronUp
                                 size={13}
                                 strokeWidth={2.5}
                              />
                              {e.up}
                           </button>
                           <button
                              style={{
                                 display: "flex",
                                 alignItems: "center",
                                 gap: 5,
                                 background: "#fef2f2",
                                 border: "1.5px solid #fecaca",
                                 borderRadius: 6,
                                 padding: "4px 10px",
                                 cursor: "pointer",
                                 fontSize: 11,
                                 fontWeight: 700,
                                 color: "#991b1b",
                              }}>
                              <ChevronDown
                                 size={13}
                                 strokeWidth={2.5}
                              />
                              {e.down}
                           </button>
                           <span
                              style={{
                                 fontSize: 9,
                                 color: T.gray,
                                 marginLeft: 4,
                                 display: "flex",
                                 alignItems: "center",
                                 gap: 3,
                              }}>
                              <Hash
                                 size={9}
                                 color={T.gray}
                              />
                              Weighted: {(e.up * (e.score / 100) - e.down * 0.5).toFixed(1)}
                           </span>
                        </div>
                     </div>
                  ))}
               </div>
            )}
         </div>
      </div>
   );
};

// ─── Design System ────────────────────────────────────────────────────────────
const DesignSystem = () => (
   <div>
      <SLabel>Color System & Token Reference</SLabel>
      <div
         style={{
            display: "grid",
            gridTemplateColumns: "repeat(4,1fr)",
            gap: 16,
            marginBottom: 32,
         }}>
         {[
            {
               label: "Trust Indigo",
               sub: "Primary actions, active states, nav",
               hex: "#4f46e5",
               Icon: Search,
               dark: true,
            },
            {
               label: "App Background",
               sub: "bg-gray-50 · Page backgrounds",
               hex: "#f9fafb",
               Icon: Layers,
               dark: false,
            },
            {
               label: "Surface White",
               sub: "bg-white · Cards, modals, overlays",
               hex: "#ffffff",
               Icon: PanelLeft,
               dark: false,
            },
            {
               label: "Verified / Fact",
               sub: "Green · Confirmed claims, accepted evidence",
               hex: "#0e9f6e",
               Icon: CheckCircle2,
               dark: true,
            },
            {
               label: "Fake / False",
               sub: "Red · Debunked, rejected content",
               hex: "#e02424",
               Icon: XCircle,
               dark: true,
            },
            {
               label: "Misleading",
               sub: "Amber · Ambiguous, partial truth",
               hex: "#d97706",
               Icon: AlertTriangle,
               dark: true,
            },
            {
               label: "Unverified",
               sub: "Gray · Neutral, out of scope, unknown",
               hex: "#6b7280",
               Icon: HelpCircle,
               dark: true,
            },
            {
               label: "Satire",
               sub: "Violet · Intentional fiction or comedy",
               hex: "#7c3aed",
               Icon: Wand2,
               dark: true,
            },
         ].map((c) => (
            <div
               key={c.hex}
               style={{
                  background: "#fff",
                  border: "1.5px solid #e5e7eb",
                  borderRadius: 10,
                  overflow: "hidden",
               }}>
               <div
                  style={{
                     background: c.hex,
                     height: 64,
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "space-between",
                     padding: "0 12px",
                  }}>
                  <c.Icon
                     size={20}
                     color={c.dark ? "rgba(255,255,255,0.85)" : "#9ca3af"}
                     strokeWidth={1.8}
                  />
                  <code
                     style={{
                        fontSize: 10,
                        fontWeight: 800,
                        color: c.dark ? "rgba(255,255,255,0.9)" : "#374151",
                        fontFamily: "monospace",
                     }}>
                     {c.hex}
                  </code>
               </div>
               <div style={{ padding: "8px 12px" }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#111827" }}>{c.label}</div>
                  <div style={{ fontSize: 10, color: T.gray, marginTop: 2 }}>{c.sub}</div>
               </div>
            </div>
         ))}
      </div>
      <SLabel>Verdict Badge States</SLabel>
      <div
         style={{
            background: "#fff",
            border: "1.5px solid #e5e7eb",
            borderRadius: 10,
            padding: 20,
            display: "flex",
            gap: 12,
            flexWrap: "wrap",
            marginBottom: 24,
            alignItems: "center",
         }}>
         {["verified", "fake", "misleading", "unverified", "satire"].map((v) => (
            <VerdictBadge
               key={v}
               verdict={v}
            />
         ))}
      </div>
      <SLabel>Icon Usage Reference</SLabel>
      <div
         style={{
            background: "#fff",
            border: "1.5px solid #e5e7eb",
            borderRadius: 10,
            padding: 20,
            marginBottom: 24,
         }}>
         <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10 }}>
            {[
               [Search, "Brand / Scan URL"],
               [Scissors, "Snip Tool"],
               [Upload, "File Upload"],
               [Crosshair, "Screen Capture"],
               [CheckCircle2, "Verified Verdict"],
               [XCircle, "Fake Verdict"],
               [AlertTriangle, "Misleading Verdict"],
               [HelpCircle, "Unverified Verdict"],
               [Wand2, "Satire Verdict"],
               [MessageCircle, "Comments"],
               [Paperclip, "Evidence"],
               [ThumbsUp, "Upvote / React"],
               [ChevronUp, "Evidence Upvote"],
               [ChevronDown, "Evidence Downvote"],
               [Shield, "Moderator Badge"],
               [Trophy, "Trust Reward"],
               [BadgeCheck, "Verified Contributor"],
               [Star, "Top Evidence"],
               [TrendingUp, "Trending Filter"],
               [MoreHorizontal, "Post Options Menu"],
            ].map(([Ic, label]) => (
               <div
                  key={label}
                  style={{
                     display: "flex",
                     alignItems: "center",
                     gap: 10,
                     padding: "8px 10px",
                     background: "#f9fafb",
                     borderRadius: 8,
                  }}>
                  <div
                     style={{
                        width: 30,
                        height: 30,
                        background: "#fff",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 7,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                     }}>
                     <Ic
                        size={15}
                        color={T.indigo}
                        strokeWidth={2}
                     />
                  </div>
                  <span style={{ fontSize: 11, color: "#374151", fontWeight: 600 }}>{label}</span>
               </div>
            ))}
         </div>
      </div>
      <SLabel>Typography Scale</SLabel>
      <div
         style={{
            background: "#fff",
            border: "1.5px solid #e5e7eb",
            borderRadius: 10,
            padding: 20,
         }}>
         {[
            [
               "text-2xl font-black tracking-tight",
               "Page Titles — 24px / 900 weight",
               "#111827",
               900,
            ],
            ["text-lg font-bold", "Section Headers — 18px / 700 weight", "#1f2937", 700],
            ["text-sm font-semibold", "Body Labels — 14px / 600 weight", "#374151", 600],
            [
               "text-xs font-medium text-gray-500",
               "Meta / Timestamps — 12px / 500 weight",
               T.gray,
               500,
            ],
            [
               "text-[10px] font-bold tracking-widest uppercase",
               "Section Tags — 10px ALL CAPS",
               T.indigo,
               800,
            ],
         ].map(([cls, label, color, w]) => (
            <div
               key={label}
               style={{
                  display: "flex",
                  gap: 16,
                  alignItems: "baseline",
                  marginBottom: 10,
                  paddingBottom: 10,
                  borderBottom: "1px solid #f3f4f6",
               }}>
               <span style={{ fontSize: 14, color, fontWeight: w }}>{label}</span>
               <code
                  style={{
                     fontSize: 9,
                     background: "#f3f4f6",
                     padding: "2px 6px",
                     borderRadius: 4,
                     color: T.gray,
                     fontFamily: "monospace",
                     marginLeft: "auto",
                     flexShrink: 0,
                  }}>
                  {cls}
               </code>
            </div>
         ))}
      </div>
   </div>
);

// ─── Root App ─────────────────────────────────────────────────────────────────
const VIEWS = [
   { id: "design", Icon: Palette, label: "Design System" },
   { id: "ext-popup", Icon: ScanLine, label: "Ext. Popup" },
   { id: "ext-cards", Icon: Layers, label: "Injection Cards" },
   { id: "auth", Icon: Shield, label: "Auth Pages" },
   { id: "dashboard", Icon: LayoutDashboard, label: "Dashboard" },
   { id: "feed", Icon: Globe, label: "Community Feed" },
   { id: "thread", Icon: MessageCircle, label: "Thread Detail" },
];
const DESC = {
   design:
      "Token reference, verdict states, icon map, and typography scale for the entire TruthLens platform.",
   "ext-popup": "380×520px popup with 3 tabbed input modes: Snip, Upload, and Scan URL.",
   "ext-cards":
      "React portals injected into host pages — Loading state and Analysis Result states.",
   auth: "Minimalist entry point with optional value proposition for new users.",
   dashboard:
      "User's personal space: Profile + Trust Score gauge, scan history, and contributions.",
   feed: "Facebook-style post feed with snipped images, verdict overlays, and reaction/action rows.",
   thread:
      "Full post view with collapsible evidence form and tabbed Comments / Evidence Board section.",
};
const TITLE = {
   design: "Design System Reference",
   "ext-popup": "The Browser Extension Popup",
   "ext-cards": "Content Script Injection Cards",
   auth: "Authentication Pages",
   dashboard: "Personal Dashboard",
   feed: "Community Feed",
   thread: "Thread Detail Page",
};

export default function TruthLensWireframes() {
   const [active, setActive] = useState("design");
   const v = VIEWS.find((v) => v.id === active);
   return (
      <div
         style={{
            fontFamily: "'DM Sans','Segoe UI',sans-serif",
            background: "#f1f5f9",
            minHeight: "100vh",
            width: "100vw",
         }}>
         {/* Nav */}
         <div
            style={{
               background: T.dark,
               padding: "0 24px",
               display: "flex",
               alignItems: "center",
               position: "sticky",
               top: 0,
               zIndex: 100,
               boxShadow: "0 2px 16px rgba(0,0,0,0.25)",
            }}>
            <div
               style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "12px 0",
                  marginRight: 24,
                  borderRight: "1px solid rgba(255,255,255,0.08)",
                  paddingRight: 24,
               }}>
               <Logo size={16} />
               <div>
                  <div
                     style={{
                        color: "#fff",
                        fontWeight: 900,
                        fontSize: 15,
                        letterSpacing: "-0.01em",
                     }}>
                     TruthLens
                  </div>
                  <div
                     style={{
                        color: "rgba(255,255,255,0.35)",
                        fontSize: 9,
                        letterSpacing: "0.1em",
                     }}>
                     WIREFRAME BLUEPRINTS
                  </div>
               </div>
            </div>
            <div style={{ display: "flex", overflowX: "auto", gap: 2, flex: 1 }}>
               {VIEWS.map(({ id, Icon: VI, label }) => (
                  <button
                     key={id}
                     onClick={() => setActive(id)}
                     style={{
                        padding: "14px 12px",
                        fontSize: 11,
                        fontWeight: 600,
                        background: "transparent",
                        border: "none",
                        borderBottom:
                           active === id ? `2px solid ${T.indigo}` : "2px solid transparent",
                        color: active === id ? "#fff" : "rgba(255,255,255,0.5)",
                        cursor: "pointer",
                        whiteSpace: "nowrap",
                        transition: "all 0.15s",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                     }}>
                     <VI
                        size={13}
                        strokeWidth={2}
                     />
                     {label}
                  </button>
               ))}
            </div>
            <div
               style={{
                  padding: "6px 12px",
                  background: "rgba(79,70,229,0.3)",
                  borderRadius: 6,
                  border: "1px solid rgba(79,70,229,0.5)",
                  flexShrink: 0,
               }}>
               <span
                  style={{
                     fontSize: 10,
                     color: "rgba(255,255,255,0.7)",
                     fontWeight: 600,
                     letterSpacing: "0.06em",
                  }}>
                  UI/UX GUIDE v1.0
               </span>
            </div>
         </div>
         {/* Content */}
         <div style={{ padding: "32px 32px 48px", maxWidth: 1200, margin: "0 auto" }}>
            <div style={{ marginBottom: 28 }}>
               <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                  <div
                     style={{
                        width: 32,
                        height: 32,
                        background: T.indigo,
                        borderRadius: 8,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                     }}>
                     <v.Icon
                        size={16}
                        color="#fff"
                        strokeWidth={2}
                     />
                  </div>
                  <span
                     style={{
                        fontSize: 11,
                        color: T.indigo,
                        fontWeight: 800,
                        letterSpacing: "0.1em",
                        textTransform: "uppercase",
                     }}>
                     {v.label}
                  </span>
               </div>
               <div
                  style={{
                     fontSize: 24,
                     fontWeight: 900,
                     color: T.dark,
                     letterSpacing: "-0.02em",
                  }}>
                  {TITLE[active]}
               </div>
               <div style={{ fontSize: 13, color: T.gray, marginTop: 4 }}>{DESC[active]}</div>
            </div>
            {active === "design" && <DesignSystem />}
            {active === "ext-popup" && <ExtensionPopup />}
            {active === "ext-cards" && <ContentCards />}
            {active === "auth" && <AuthPages />}
            {active === "dashboard" && <PersonalDashboard />}
            {active === "feed" && <CommunityFeed />}
            {active === "thread" && (
               <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 32 }}>
                  <ThreadDetail />
                  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                     <Ann
                        title="Visual Structure"
                        BoxIcon={Ruler}
                        color={T.indigo}
                        items={[
                           "PostCard (identical to feed) → EvidenceToggleBtn → CollapsibleForm → TabbedSection",
                           "TabbedSection: [Comments | Evidence Board] — Comments default active",
                           "Evidence form hidden by default, toggled by Submit Evidence button",
                           "Form merges below button via shared border — borderTop: none",
                           "Max-width ~600px — mobile-first single column layout",
                        ]}
                     />
                     <Ann
                        title="React Components"
                        BoxIcon={Braces}
                        color="#7c3aed"
                        items={[
                           "<ThreadDetail> — fetches thread by :id, owns showForm + activeTab state",
                           "<PostCard> — reused from Community Feed (no changes needed)",
                           "<EvidenceToggleButton> — toggles showEvidenceForm boolean",
                           "<EvidenceFormPanel> — conditionally rendered, controlled inputs",
                           "<TabbedSection> — renders tab bar + active panel",
                           "<CommentsPanel> — CommentInput + CommentList + CommentItem",
                           "<EvidenceBoardPanel> — sorted EvidenceCard list",
                           "<EvidenceCard> — trust tier border, source link, VoteButtons",
                           "<VoteButtons> — optimistic up/down state",
                        ]}
                     />
                     <Ann
                        title="UX / Tailwind Advice"
                        BoxIcon={Palette}
                        color={T.green}
                        items={[
                           "Toggle btn: bg/border/text flips when open (visual state feedback)",
                           "Collapsible form: border-t-none merges with button above",
                           "Tab bar: border-b-2 border-indigo-600 pattern = same as Extension",
                           "Comment bubble: bg-gray-50 rounded-tr-xl rounded-b-xl (FB-style)",
                           "Evidence border-l-4 tier: green ≥75 · amber 45–74 · red <45",
                        ]}
                     />
                     <Ann
                        title="Interaction Flow"
                        BoxIcon={Hash}
                        color={T.red}
                        items={[
                           "Feed 'Add Evidence' → Thread Detail, auto-sets showForm=true",
                           "Feed 'Comment' → Thread Detail, activeTab='comments'",
                           "Submitting form → optimistic add to Evidence Board, switch tab",
                           "Tab switch is instant — data already in component state",
                           "Evidence sorted: weighted_score DESC on initial load",
                        ]}
                     />
                  </div>
               </div>
            )}
         </div>
      </div>
   );
}
