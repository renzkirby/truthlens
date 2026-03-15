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
   Bell,
   BellOff,
   Lock,
   Mail,
   Smartphone,
   Download,
   Zap,
   Activity,
   ChevronRight,
   Info,
   ToggleLeft,
   ToggleRight,
   PieChart,
   Minimize2,
   AlertOctagon,
   ListChecks,
   Rocket,
   Play,
   MonitorSmartphone,
   Check,
   Trash2,
   RefreshCw,
   Volume2,
   VolumeX,
   Send,
   ArrowLeft,
   UserCheck,
   Clock,
   Circle,
   LogOut,
   PlusCircle,
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

// ─── Browser Chrome wrapper (reused by Feed, Thread, Auth) ───────────────────
const BrowserChrome = ({ url, children }) => (
   <div
      style={{
         overflow: "hidden",
         borderTop: "1px solid #d1d5db",
         borderBottom: "1px solid #d1d5db",
         boxShadow: "0 8px 40px rgba(0,0,0,0.18)",
      }}>
      {/* Title bar */}
      <div
         style={{
            background: "#e8e8e8",
            padding: "10px 16px",
            display: "flex",
            alignItems: "center",
            gap: 12,
            borderBottom: "1px solid #d0d0d0",
         }}>
         {/* Traffic lights */}
         <div style={{ display: "flex", gap: 6 }}>
            {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
               <div
                  key={c}
                  style={{ width: 12, height: 12, borderRadius: "50%", background: c }}
               />
            ))}
         </div>
         {/* Nav arrows */}
         <div style={{ display: "flex", gap: 4 }}>
            <div
               style={{
                  width: 24,
                  height: 24,
                  borderRadius: 5,
                  background: "#d0d0d0",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
               }}>
               <ArrowRight
                  size={11}
                  color="#888"
                  style={{ transform: "rotate(180deg)" }}
               />
            </div>
            <div
               style={{
                  width: 24,
                  height: 24,
                  borderRadius: 5,
                  background: "#d0d0d0",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  opacity: 0.4,
               }}>
               <ArrowRight
                  size={11}
                  color="#888"
               />
            </div>
         </div>
         {/* Address bar */}
         <div
            style={{
               flex: 1,
               background: "#fff",
               borderRadius: 6,
               padding: "5px 14px",
               fontSize: 12,
               color: "#555",
               display: "flex",
               alignItems: "center",
               gap: 8,
               border: "1px solid #c8c8c8",
            }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
               <div
                  style={{
                     width: 12,
                     height: 12,
                     borderRadius: "50%",
                     background: T.green,
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "center",
                  }}>
                  <Shield
                     size={7}
                     color="#fff"
                     strokeWidth={3}
                  />
               </div>
               <span style={{ fontSize: 11, color: "#999" }}>https://</span>
            </div>
            <span style={{ fontWeight: 600, color: "#333" }}>truthlens.app</span>
            <span style={{ color: "#999" }}>/{url}</span>
         </div>
         {/* Browser icons */}
         <div style={{ display: "flex", gap: 4 }}>
            {[Search, Star, MoreHorizontal].map((BI, i) => (
               <div
                  key={i}
                  style={{
                     width: 26,
                     height: 26,
                     borderRadius: 5,
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "center",
                  }}>
                  <BI
                     size={14}
                     color="#666"
                     strokeWidth={1.8}
                  />
               </div>
            ))}
         </div>
      </div>
      {/* Viewport */}
      <div style={{ background: "#f1f5f9", minHeight: "calc(100vh - 160px)", overflowY: "auto" }}>
         {children}
      </div>
   </div>
);

// Simulated in-page TruthLens app nav (shown inside the browser viewport)
const AppNav = ({ activePage = "feed" }) => {
   const [dropdownOpen, setDropdownOpen] = useState(false);
   const pages = [
      { id: "feed", Icon: Globe, label: "Community Feed" },
      { id: "dashboard", Icon: LayoutDashboard, label: "Dashboard" },
      { id: "notifications", Icon: Bell, label: "Notifications" },
      { id: "settings", Icon: Settings, label: "Settings" },
   ];
   const menuItems = [
      { Icon: UserCircle, label: "View Profile", action: "profile" },
      { Icon: LayoutDashboard, label: "Dashboard", action: "dashboard" },
      { Icon: Settings, label: "Settings", action: "settings" },
   ];
   return (
      <div
         style={{
            background: T.dark,
            padding: "0 32px",
            display: "flex",
            alignItems: "center",
            boxShadow: "0 2px 12px rgba(0,0,0,0.25)",
            position: "sticky",
            top: 0,
            zIndex: 50,
         }}>
         {/* Logo */}
         <div
            style={{
               display: "flex",
               alignItems: "center",
               gap: 10,
               padding: "12px 0",
               marginRight: 28,
               borderRight: "1px solid rgba(255,255,255,0.08)",
               paddingRight: 28,
            }}>
            <Logo size={14} />
            <span
               style={{ color: "#fff", fontWeight: 900, fontSize: 15, letterSpacing: "-0.01em" }}>
               TruthLens
            </span>
         </div>
         {/* Nav links */}
         <div style={{ display: "flex", gap: 2, flex: 1 }}>
            {pages.map(({ id, Icon: NI, label }) => (
               <div
                  key={id}
                  style={{
                     padding: "12px 14px",
                     fontSize: 12,
                     fontWeight: 600,
                     display: "flex",
                     alignItems: "center",
                     gap: 7,
                     color: activePage === id ? "#fff" : "rgba(255,255,255,0.45)",
                     borderBottom:
                        activePage === id ? `2px solid ${T.indigo}` : "2px solid transparent",
                     cursor: "pointer",
                  }}>
                  <NI
                     size={13}
                     strokeWidth={activePage === id ? 2.5 : 2}
                  />
                  {label}
               </div>
            ))}
         </div>
         {/* Profile pill + dropdown */}
         <div style={{ position: "relative" }}>
            <div
               onClick={() => setDropdownOpen((v) => !v)}
               style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 7,
                  background: dropdownOpen ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.07)",
                  borderRadius: 8,
                  padding: "6px 12px",
                  cursor: "pointer",
                  userSelect: "none",
               }}>
               <Avatar
                  Icon={UserCircle}
                  bg="rgba(255,255,255,0.12)"
                  color="rgba(255,255,255,0.7)"
                  size={26}
               />
               <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.8)" }}>
                  @verifyme
               </span>
               <span
                  style={{
                     fontSize: 11,
                     fontWeight: 800,
                     color: T.green,
                     background: "rgba(14,159,110,0.15)",
                     borderRadius: 6,
                     padding: "2px 7px",
                     border: `1px solid rgba(14,159,110,0.3)`,
                  }}>
                  82
               </span>
               <ChevronDown
                  size={13}
                  color="rgba(255,255,255,0.4)"
                  style={{
                     transform: dropdownOpen ? "rotate(180deg)" : "rotate(0deg)",
                     transition: "transform 0.15s",
                  }}
               />
            </div>

            {/* Dropdown menu */}
            {dropdownOpen && (
               <div
                  style={{
                     position: "absolute",
                     top: "calc(100% + 8px)",
                     right: 0,
                     background: "#fff",
                     borderRadius: 12,
                     boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
                     border: "1px solid #e5e7eb",
                     minWidth: 200,
                     overflow: "hidden",
                     zIndex: 100,
                  }}>
                  {/* User info header */}
                  <div
                     style={{
                        padding: "14px 16px",
                        borderBottom: "1px solid #f3f4f6",
                        background: "#f9fafb",
                     }}>
                     <div style={{ fontSize: 13, fontWeight: 800, color: "#111827" }}>
                        @verifyme
                     </div>
                     <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>
                        verifyme@email.com
                     </div>
                  </div>
                  {/* Nav items */}
                  <div style={{ padding: "6px 0" }}>
                     {menuItems.map(({ Icon: MI, label, action }) => (
                        <div
                           key={action}
                           style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 10,
                              padding: "9px 16px",
                              fontSize: 13,
                              fontWeight: 600,
                              color: "#374151",
                              cursor: "pointer",
                           }}
                           onMouseEnter={(e) => (e.currentTarget.style.background = "#f9fafb")}
                           onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                           <MI
                              size={14}
                              color={T.gray}
                              strokeWidth={2}
                           />
                           {label}
                        </div>
                     ))}
                  </div>
                  {/* Divider */}
                  <div style={{ height: 1, background: "#f3f4f6", margin: "4px 0" }} />
                  {/* Log out — separated, destructive */}
                  <div style={{ padding: "6px 0 8px" }}>
                     <div
                        style={{
                           display: "flex",
                           alignItems: "center",
                           gap: 10,
                           padding: "9px 16px",
                           fontSize: 13,
                           fontWeight: 700,
                           color: T.red,
                           cursor: "pointer",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "#fef2f2")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                        <LogOut
                           size={14}
                           color={T.red}
                           strokeWidth={2}
                        />
                        Log Out
                     </div>
                  </div>
               </div>
            )}
         </div>
      </div>
   );
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

   const orbs = [
      { w: 280, h: 280, top: "-80px", left: "-80px", opacity: 0.1 },
      { w: 200, h: 200, top: "55%", left: "62%", opacity: 0.08 },
      { w: 120, h: 120, top: "78%", left: "8%", opacity: 0.06 },
      { w: 320, h: 320, top: "-10%", left: "58%", opacity: 0.07 },
   ];
   const stats = [
      { Icon: ScanLine, value: "128K+", label: "Claims Analyzed" },
      { Icon: CheckCircle2, value: "94K+", label: "Facts Verified" },
      { Icon: Users, value: "32K+", label: "Community Members" },
   ];
   const features = [
      { Icon: Shield, text: "AI-powered claim detection in real time" },
      { Icon: Users, text: "Community-driven evidence and voting" },
      { Icon: Trophy, text: "Earn Trust Score by contributing verified facts" },
      { Icon: BadgeCheck, text: "Browser extension for on-the-fly fact-checking" },
   ];

   // ── Shared left + right panels ──────────────────────────────────────────────
   const LeftPanel = () => (
      <div
         style={{
            background: `linear-gradient(160deg, ${T.dark} 0%, #2d2a6e 60%, ${T.indigo} 100%)`,
            padding: "52px 48px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            position: "relative",
            overflow: "hidden",
            flex: 1,
         }}>
         {orbs.map((o, i) => (
            <div
               key={i}
               style={{
                  position: "absolute",
                  width: o.w,
                  height: o.h,
                  top: o.top,
                  left: o.left,
                  borderRadius: "50%",
                  background: "rgba(255,255,255,0.9)",
                  opacity: o.opacity,
                  pointerEvents: "none",
               }}
            />
         ))}
         <svg
            style={{
               position: "absolute",
               inset: 0,
               width: "100%",
               height: "100%",
               opacity: 0.055,
            }}
            xmlns="http://www.w3.org/2000/svg">
            <defs>
               <pattern
                  id="dots2"
                  x="0"
                  y="0"
                  width="28"
                  height="28"
                  patternUnits="userSpaceOnUse">
                  <circle
                     cx="2"
                     cy="2"
                     r="1.8"
                     fill="white"
                  />
               </pattern>
            </defs>
            <rect
               width="100%"
               height="100%"
               fill="url(#dots2)"
            />
         </svg>

         <div style={{ position: "relative", zIndex: 1 }}>
            {/* Logo */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 56 }}>
               <Logo
                  size={20}
                  bg="rgba(255,255,255,0.15)"
               />
               <span
                  style={{
                     color: "#fff",
                     fontWeight: 900,
                     fontSize: 20,
                     letterSpacing: "-0.02em",
                  }}>
                  TruthLens
               </span>
            </div>
            {/* Headline */}
            <div style={{ marginBottom: 40 }}>
               <div
                  style={{
                     fontSize: 32,
                     fontWeight: 900,
                     color: "#fff",
                     lineHeight: 1.2,
                     letterSpacing: "-0.03em",
                     marginBottom: 14,
                  }}>
                  {mode === "login" ? (
                     <>
                        The Internet
                        <br />
                        Deserves
                        <br />
                        the Truth.
                     </>
                  ) : (
                     <>
                        Join the Fight
                        <br />
                        Against
                        <br />
                        Misinformation.
                     </>
                  )}
               </div>
               <p
                  style={{
                     fontSize: 13,
                     color: "rgba(255,255,255,0.55)",
                     lineHeight: 1.8,
                     margin: 0,
                     maxWidth: 280,
                  }}>
                  {mode === "login"
                     ? "Welcome back. Your community is counting on you to keep the information ecosystem honest."
                     : "Create your account and start earning Trust Score by verifying claims alongside a global community."}
               </p>
            </div>
            {/* Dynamic content */}
            {mode === "register" ? (
               <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {features.map(({ Icon: FI, text }) => (
                     <div
                        key={text}
                        style={{ display: "flex", alignItems: "center", gap: 14 }}>
                        <div
                           style={{
                              width: 34,
                              height: 34,
                              borderRadius: 10,
                              background: "rgba(255,255,255,0.1)",
                              border: "1px solid rgba(255,255,255,0.12)",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              flexShrink: 0,
                           }}>
                           <FI
                              size={16}
                              color="rgba(255,255,255,0.85)"
                              strokeWidth={2}
                           />
                        </div>
                        <span
                           style={{
                              fontSize: 13,
                              color: "rgba(255,255,255,0.7)",
                              lineHeight: 1.5,
                           }}>
                           {text}
                        </span>
                     </div>
                  ))}
               </div>
            ) : (
               <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {stats.map(({ Icon: SI, value, label }) => (
                     <div
                        key={label}
                        style={{
                           display: "flex",
                           alignItems: "center",
                           gap: 16,
                           background: "rgba(255,255,255,0.07)",
                           borderRadius: 12,
                           padding: "14px 18px",
                           border: "1px solid rgba(255,255,255,0.1)",
                        }}>
                        <div
                           style={{
                              width: 38,
                              height: 38,
                              borderRadius: 10,
                              background: "rgba(255,255,255,0.12)",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              flexShrink: 0,
                           }}>
                           <SI
                              size={18}
                              color="#fff"
                              strokeWidth={2}
                           />
                        </div>
                        <div>
                           <div
                              style={{
                                 fontSize: 20,
                                 fontWeight: 900,
                                 color: "#fff",
                                 letterSpacing: "-0.02em",
                                 lineHeight: 1,
                              }}>
                              {value}
                           </div>
                           <div
                              style={{
                                 fontSize: 11,
                                 color: "rgba(255,255,255,0.45)",
                                 fontWeight: 500,
                                 marginTop: 2,
                              }}>
                              {label}
                           </div>
                        </div>
                     </div>
                  ))}
               </div>
            )}
         </div>

         <div style={{ position: "relative", zIndex: 1, marginTop: 40 }}>
            <div
               style={{ height: "1px", background: "rgba(255,255,255,0.08)", marginBottom: 16 }}
            />
            <div
               style={{
                  fontSize: 10,
                  color: "rgba(255,255,255,0.3)",
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
               }}>
               www.truthlens.app
            </div>
         </div>
      </div>
   );

   const RightPanel = () => (
      <div
         style={{
            background: "#fff",
            padding: "52px 56px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            flex: 1,
         }}>
         <div style={{ maxWidth: 380, width: "100%", margin: "0 auto" }}>
            {/* Greeting */}
            <div style={{ marginBottom: 36 }}>
               <div style={{ fontSize: 14, color: T.gray, fontWeight: 500, marginBottom: 6 }}>
                  {mode === "login" ? "Hello! Welcome back." : "Hello! Let's get started."}
               </div>
               <div
                  style={{
                     fontSize: 28,
                     fontWeight: 900,
                     color: T.dark,
                     letterSpacing: "-0.03em",
                     lineHeight: 1.15,
                  }}>
                  {mode === "login" ? (
                     <>
                        <span style={{ color: T.indigo }}>Sign in</span> to your account
                     </>
                  ) : (
                     <>
                        <span style={{ color: T.indigo }}>Create</span> your account
                     </>
                  )}
               </div>
            </div>

            {/* Fields */}
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
               {mode === "register" && (
                  <div>
                     <label
                        style={{
                           fontSize: 12,
                           fontWeight: 700,
                           color: "#374151",
                           display: "block",
                           marginBottom: 6,
                        }}>
                        Username
                     </label>
                     <div
                        style={{
                           background: "#f9fafb",
                           borderBottom: `2px solid ${T.indigo}`,
                           borderTop: "1.5px solid #e5e7eb",
                           borderLeft: "1.5px solid #e5e7eb",
                           borderRight: "1.5px solid #e5e7eb",
                           borderRadius: "8px 8px 0 0",
                           padding: "12px 14px",
                           fontSize: 13,
                           color: "#9ca3af",
                           display: "flex",
                           alignItems: "center",
                           gap: 8,
                        }}>
                        <User
                           size={14}
                           color="#9ca3af"
                        />
                        Choose a unique username…
                     </div>
                  </div>
               )}
               <div>
                  <label
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: "#374151",
                        display: "block",
                        marginBottom: 6,
                     }}>
                     Email Address
                  </label>
                  <div
                     style={{
                        background: "#f9fafb",
                        borderBottom: `2px solid ${T.indigo}`,
                        borderTop: "1.5px solid #e5e7eb",
                        borderLeft: "1.5px solid #e5e7eb",
                        borderRight: "1.5px solid #e5e7eb",
                        borderRadius: "8px 8px 0 0",
                        padding: "12px 14px",
                        fontSize: 13,
                        color: "#9ca3af",
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                     }}>
                     <Layers
                        size={14}
                        color="#9ca3af"
                     />
                     you@example.com
                  </div>
               </div>
               <div>
                  <label
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: "#374151",
                        display: "block",
                        marginBottom: 6,
                     }}>
                     Password
                  </label>
                  <div
                     style={{
                        background: "#f9fafb",
                        borderBottom: `2px solid ${T.indigo}`,
                        borderTop: "1.5px solid #e5e7eb",
                        borderLeft: "1.5px solid #e5e7eb",
                        borderRight: "1.5px solid #e5e7eb",
                        borderRadius: "8px 8px 0 0",
                        padding: "12px 14px",
                        fontSize: 13,
                        color: "#9ca3af",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                     }}>
                     <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <Shield
                           size={14}
                           color="#9ca3af"
                        />
                        ••••••••••
                     </div>
                     <div
                        style={{
                           display: "flex",
                           alignItems: "center",
                           gap: 4,
                           fontSize: 11,
                           color: T.indigo,
                           cursor: "pointer",
                           fontWeight: 600,
                        }}>
                        <Eye
                           size={12}
                           color={T.indigo}
                        />
                        Show
                     </div>
                  </div>
               </div>

               {mode === "login" && (
                  <div
                     style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                     }}>
                     <label
                        style={{
                           display: "flex",
                           alignItems: "center",
                           gap: 7,
                           fontSize: 12,
                           color: T.gray,
                           cursor: "pointer",
                        }}>
                        <div
                           style={{
                              width: 16,
                              height: 16,
                              border: `1.5px solid #d1d5db`,
                              borderRadius: 4,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                           }}>
                           <div
                              style={{ width: 8, height: 8, background: T.indigo, borderRadius: 2 }}
                           />
                        </div>
                        Remember me
                     </label>
                     <a
                        style={{
                           fontSize: 12,
                           color: T.indigo,
                           cursor: "pointer",
                           fontWeight: 600,
                        }}>
                        Forgot Password?
                     </a>
                  </div>
               )}

               <button
                  style={{
                     background: T.indigo,
                     color: "#fff",
                     border: "none",
                     borderRadius: 10,
                     padding: "14px",
                     fontSize: 14,
                     fontWeight: 800,
                     cursor: "pointer",
                     letterSpacing: "0.05em",
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "center",
                     gap: 9,
                     marginTop: 4,
                  }}>
                  {mode === "login" ? "SIGN IN" : "CREATE ACCOUNT"}
                  <ArrowRight
                     size={16}
                     strokeWidth={2.5}
                  />
               </button>
            </div>

            <div style={{ textAlign: "center", marginTop: 22, fontSize: 12, color: T.gray }}>
               {mode === "login" ? (
                  <span>
                     Don't have an account?{" "}
                     <a
                        style={{ color: T.indigo, fontWeight: 700, cursor: "pointer" }}
                        onClick={() => setMode("register")}>
                        Create Account
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

            {/* OAuth divider */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "24px 0 0" }}>
               <div style={{ flex: 1, height: 1, background: "#f0f0f0" }} />
               <span
                  style={{
                     fontSize: 10,
                     color: "#9ca3af",
                     fontWeight: 700,
                     letterSpacing: "0.06em",
                  }}>
                  OR CONTINUE WITH
               </span>
               <div style={{ flex: 1, height: 1, background: "#f0f0f0" }} />
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 14 }}>
               {["Google", "GitHub"].map((p) => (
                  <button
                     key={p}
                     style={{
                        flex: 1,
                        padding: "11px",
                        background: "#f9fafb",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 10,
                        fontSize: 12,
                        fontWeight: 700,
                        color: "#374151",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 7,
                     }}>
                     <Globe
                        size={14}
                        color={T.gray}
                        strokeWidth={2}
                     />
                     {p}
                  </button>
               ))}
            </div>
         </div>
      </div>
   );

   return (
      <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
         {/* Mode toggle */}
         <div
            style={{
               display: "flex",
               gap: 8,
               marginBottom: 16,
               alignItems: "center",
               padding: "0 32px",
            }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: T.gray }}>Preview mode:</span>
            {["login", "register"].map((m) => (
               <button
                  key={m}
                  onClick={() => setMode(m)}
                  style={{
                     padding: "5px 18px",
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
            <span style={{ fontSize: 10, color: "#9ca3af", marginLeft: 8 }}>
               — Click to toggle between pages
            </span>
         </div>

         {/* ── Browser Chrome Frame — full bleed ── */}
         <div
            style={{
               overflow: "hidden",
               boxShadow: "0 8px 40px rgba(0,0,0,0.2)",
               borderTop: "1px solid #d1d5db",
               borderBottom: "1px solid #d1d5db",
            }}>
            {/* Browser top bar */}
            <div
               style={{
                  background: "#e8e8e8",
                  padding: "10px 16px",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  borderBottom: "1px solid #d0d0d0",
               }}>
               {/* Window buttons */}
               <div style={{ display: "flex", gap: 6 }}>
                  {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
                     <div
                        key={c}
                        style={{ width: 12, height: 12, borderRadius: "50%", background: c }}
                     />
                  ))}
               </div>
               {/* Nav arrows */}
               <div style={{ display: "flex", gap: 4 }}>
                  <div
                     style={{
                        width: 24,
                        height: 24,
                        borderRadius: 5,
                        background: "#d0d0d0",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                     }}>
                     <ArrowRight
                        size={11}
                        color="#888"
                        style={{ transform: "rotate(180deg)" }}
                     />
                  </div>
                  <div
                     style={{
                        width: 24,
                        height: 24,
                        borderRadius: 5,
                        background: "#d0d0d0",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        opacity: 0.4,
                     }}>
                     <ArrowRight
                        size={11}
                        color="#888"
                     />
                  </div>
               </div>
               {/* Address bar */}
               <div
                  style={{
                     flex: 1,
                     background: "#fff",
                     borderRadius: 6,
                     padding: "5px 14px",
                     fontSize: 12,
                     color: "#555",
                     display: "flex",
                     alignItems: "center",
                     gap: 8,
                     border: "1px solid #c8c8c8",
                  }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                     <div
                        style={{
                           width: 12,
                           height: 12,
                           borderRadius: "50%",
                           background: T.green,
                           display: "flex",
                           alignItems: "center",
                           justifyContent: "center",
                        }}>
                        <Shield
                           size={7}
                           color="#fff"
                           strokeWidth={3}
                        />
                     </div>
                     <span style={{ fontSize: 11, color: "#999" }}>https://</span>
                  </div>
                  <span style={{ fontWeight: 600, color: "#333" }}>truthlens.app</span>
                  <span style={{ color: "#999" }}>/{mode === "login" ? "login" : "register"}</span>
               </div>
               {/* Browser action icons */}
               <div style={{ display: "flex", gap: 6 }}>
                  {[Search, Star, MoreHorizontal].map((BI, i) => (
                     <div
                        key={i}
                        style={{
                           width: 26,
                           height: 26,
                           borderRadius: 5,
                           display: "flex",
                           alignItems: "center",
                           justifyContent: "center",
                           background: "transparent",
                           cursor: "pointer",
                        }}>
                        <BI
                           size={14}
                           color="#666"
                           strokeWidth={1.8}
                        />
                     </div>
                  ))}
               </div>
            </div>

            {/* Page background — full-width desktop viewport */}
            <div
               style={{
                  background: "#e8eaf0",
                  padding: "60px 0",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  minHeight: "calc(100vh - 120px)",
               }}>
               {/* Booklet — wide card filling most of the viewport */}
               <div
                  style={{
                     display: "flex",
                     width: "90%",
                     maxWidth: 1300,
                     borderRadius: 16,
                     overflow: "hidden",
                     boxShadow: "0 24px 64px rgba(0,0,0,0.22)",
                     minHeight: 580,
                  }}>
                  <LeftPanel />
                  <RightPanel />
               </div>
            </div>
         </div>
         {/* end browser frame */}

         {/* ── Annotations below the frame ── */}
         <div
            style={{
               display: "grid",
               gridTemplateColumns: "1fr 1fr",
               gap: 16,
               marginTop: 28,
               padding: "0 32px",
            }}>
            <Ann
               title="Visual Structure"
               BoxIcon={Ruler}
               color={T.indigo}
               items={[
                  "Page bg: bg-slate-200 (or bg-gray-100) — offsets the white form panel",
                  "Booklet: flex flex-row · w-[82%] max-w-5xl · rounded-2xl shadow-2xl",
                  "Left & right panels: flex-1 — equal 50/50 split at all desktop widths",
                  "Left panel: bg-gradient from-[#1e1b4b] via-[#2d2a6e] to-indigo-600",
                  "Right panel: bg-white · px-14 py-[52px] · flex flex-col justify-center",
                  "Form centered inside right: max-w-sm mx-auto (prevents stretching on wide)",
               ]}
            />
            <Ann
               title="React Components"
               BoxIcon={Braces}
               color="#7c3aed"
               items={[
                  "<AuthPage> — owns mode state ('login' | 'register')",
                  "<BrandPanel> — entire left side, receives mode prop",
                  "<StatPill> — frosted stat card (login view)",
                  "<FeatureItem> — icon + text row (register view)",
                  "<AuthForm> — entire right side, mode + onSwitch props",
                  "<FormField> — label + underline-bottom input + error msg",
                  "<RememberForgotRow> — login-only row between fields",
                  "<OAuthRow> — divider + Google / GitHub buttons",
               ]}
            />
            <Ann
               title="UX / Tailwind Advice"
               BoxIcon={Palette}
               color={T.green}
               items={[
                  "Inputs: border-b-2 border-indigo-600 only — underline style = editorial",
                  "Submit: uppercase tracking-wider font-black — signals authority",
                  "Left panel text hierarchy: 900 headline → 500 subtext → 45% opacity meta",
                  "Orb blobs: rounded-full blur-3xl absolute pointer-events-none",
                  "Dot grid: SVG pattern at opacity-5, does not compete with copy",
                  "Focus ring on inputs: focus:outline-none focus:border-indigo-500",
                  "Tab order: Username → Email → Password → Remember → Submit",
               ]}
            />
            <Ann
               title="Left Panel Content Strategy"
               BoxIcon={Sparkles}
               color={T.violet}
               items={[
                  "Login view: 3 stat pills — social proof before the user logs in",
                  "Register view: 4 feature bullets — justifies the sign-up decision",
                  "Both views: large headline + subtext paragraph + logo + URL footer",
                  "Content swaps via mode prop — single <BrandPanel> component, no duplication",
                  "On tablet (md): left panel shrinks but stays visible",
                  "On mobile (sm): left panel hidden, form fills the full screen",
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
   return (
      <div style={{ background: "#f1f5f9", minHeight: "100%" }}>
         <AppNav activePage="dashboard" />
         {/* Page body */}
         <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px 64px" }}>
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
      <div style={{ background: "#f1f5f9", minHeight: "100%" }}>
         <AppNav activePage="feed" />
         {/* Page body — centred feed column */}
         <div style={{ maxWidth: 680, margin: "0 auto", padding: "32px 24px 64px" }}>
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
                  marginBottom: 20,
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
               }}>
               <Avatar
                  Icon={UserCircle}
                  bg="#ede9fe"
                  color={T.violet}
                  size={38}
               />
               <div
                  style={{
                     flex: 1,
                     background: "#f9fafb",
                     border: "1.5px solid #e5e7eb",
                     borderRadius: 999,
                     padding: "10px 18px",
                     fontSize: 13,
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
                     padding: "9px 16px",
                     fontSize: 12,
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
            {/* Post list */}
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

   const verdictMeta = {
      verified: {
         color: T.green,
         bg: "#ecfdf5",
         label: "Verified",
         desc: "This claim has been confirmed by multiple trusted sources.",
      },
      fake: {
         color: T.red,
         bg: "#fef2f2",
         label: "False",
         desc: "This claim has been debunked by reliable fact-checkers.",
      },
      misleading: {
         color: T.amber,
         bg: "#fffbeb",
         label: "Misleading",
         desc: "This claim contains partial truths but omits key context.",
      },
      unverified: {
         color: T.gray,
         bg: "#f9fafb",
         label: "Unverified",
         desc: "Insufficient evidence to confirm or deny this claim.",
      },
      satire: {
         color: T.violet,
         bg: "#f5f3ff",
         label: "Satire",
         desc: "This content is intentional satire or parody.",
      },
   };
   const vm = verdictMeta[post.verdict] || verdictMeta.unverified;
   const tier = (s) => (s >= 75 ? T.green : s >= 45 ? T.amber : T.red);

   // Confidence bar gradient
   const confColor = post.confidence >= 75 ? T.green : post.confidence >= 45 ? T.amber : T.red;

   return (
      <div style={{ background: "#ffffff", minHeight: "100%" }}>
         <AppNav activePage="feed" />

         {/* ── Sub-header / Back bar ─────────────────────────────────────── */}
         <div
            style={{
               background: "#fff",
               borderBottom: `3px solid ${vm.color}`,
               padding: "0 40px",
               display: "flex",
               alignItems: "center",
               gap: 16,
               height: 52,
               boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
            }}>
            {/* Back button */}
            <button
               style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: 700,
                  color: T.indigo,
                  padding: "6px 0",
               }}>
               <ArrowRight
                  size={14}
                  color={T.indigo}
                  style={{ transform: "rotate(180deg)" }}
               />
               Community Feed
            </button>
            <span style={{ color: "#e5e7eb", fontSize: 18 }}>›</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>Thread #1042</span>
            <span style={{ fontSize: 11, color: T.gray }}>·</span>
            <span style={{ fontSize: 11, color: T.gray }}>Flagged 2h ago by @photocheck</span>
            {/* Verdict badge right-aligned */}
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
               <VerdictBadge verdict={post.verdict} />
               <span
                  style={{
                     fontSize: 12,
                     color: T.gray,
                     background: "#f3f4f6",
                     borderRadius: 6,
                     padding: "3px 10px",
                     fontWeight: 600,
                  }}>
                  {post.status}
               </span>
            </div>
         </div>

         {/* ── Claim Hero ────────────────────────────────────────────────── */}
         <div
            style={{
               background: vm.bg,
               borderBottom: `1px solid ${vm.color}30`,
               padding: "36px 40px",
            }}>
            <div
               style={{
                  maxWidth: 1200,
                  margin: "0 auto",
                  display: "flex",
                  gap: 40,
                  alignItems: "center",
               }}>
               {/* Left: claim text */}
               <div style={{ flex: 1 }}>
                  <div
                     style={{
                        fontSize: 11,
                        fontWeight: 800,
                        color: vm.color,
                        letterSpacing: "0.1em",
                        textTransform: "uppercase",
                        marginBottom: 10,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                     }}>
                     <Flag
                        size={11}
                        color={vm.color}
                        strokeWidth={2.5}
                     />
                     Claim Under Investigation
                  </div>
                  <p
                     style={{
                        fontSize: 22,
                        fontWeight: 800,
                        color: "#111827",
                        lineHeight: 1.4,
                        letterSpacing: "-0.02em",
                        margin: "0 0 16px",
                        maxWidth: 680,
                     }}>
                     {post.caption}
                  </p>
                  <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                     <div
                        style={{
                           display: "flex",
                           alignItems: "center",
                           gap: 6,
                           fontSize: 12,
                           color: T.gray,
                        }}>
                        <Globe
                           size={12}
                           color={T.gray}
                        />
                        Sourced from <strong style={{ color: "#374151" }}>{post.source}</strong>
                     </div>
                     <div
                        style={{
                           display: "flex",
                           alignItems: "center",
                           gap: 6,
                           fontSize: 12,
                           color: T.gray,
                        }}>
                        <MessageCircle
                           size={12}
                           color={T.gray}
                        />
                        <strong style={{ color: "#374151" }}>{post.comments}</strong> comments
                     </div>
                     <div
                        style={{
                           display: "flex",
                           alignItems: "center",
                           gap: 6,
                           fontSize: 12,
                           color: T.gray,
                        }}>
                        <Paperclip
                           size={12}
                           color={T.gray}
                        />
                        <strong style={{ color: "#374151" }}>{post.evidence}</strong> evidence
                        submissions
                     </div>
                  </div>
               </div>

               {/* Right: verdict + confidence panel */}
               <div
                  style={{
                     background: "#fff",
                     border: `1.5px solid ${vm.color}40`,
                     borderRadius: 16,
                     padding: "24px 28px",
                     minWidth: 240,
                     boxShadow: `0 4px 20px ${vm.color}15`,
                  }}>
                  {/* Verdict */}
                  <div style={{ textAlign: "center", marginBottom: 20 }}>
                     <VerdictBadge verdict={post.verdict} />
                     <p style={{ fontSize: 11, color: T.gray, margin: "8px 0 0", lineHeight: 1.5 }}>
                        {vm.desc}
                     </p>
                  </div>
                  {/* Divider */}
                  <div style={{ height: 1, background: "#f0f0f0", margin: "0 0 16px" }} />
                  {/* Confidence */}
                  <div style={{ marginBottom: 14 }}>
                     <div
                        style={{
                           display: "flex",
                           justifyContent: "space-between",
                           alignItems: "baseline",
                           marginBottom: 6,
                        }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#374151" }}>
                           AI Confidence
                        </span>
                        <span style={{ fontSize: 18, fontWeight: 900, color: confColor }}>
                           {post.confidence}%
                        </span>
                     </div>
                     <div
                        style={{
                           height: 6,
                           background: "#f3f4f6",
                           borderRadius: 99,
                           overflow: "hidden",
                        }}>
                        <div
                           style={{
                              width: `${post.confidence}%`,
                              height: "100%",
                              background: confColor,
                              borderRadius: 99,
                           }}
                        />
                     </div>
                  </div>
                  {/* Evidence count pill */}
                  <div
                     style={{
                        background: vm.bg,
                        borderRadius: 8,
                        padding: "10px 14px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                     }}>
                     <span style={{ fontSize: 11, color: T.gray, fontWeight: 600 }}>
                        Evidence submissions
                     </span>
                     <span style={{ fontSize: 16, fontWeight: 900, color: vm.color }}>
                        {post.evidence}
                     </span>
                  </div>
               </div>
            </div>
         </div>

         {/* ── Two-column body ───────────────────────────────────────────── */}
         <div
            style={{
               maxWidth: 1200,
               margin: "0 auto",
               padding: "32px 40px 64px",
               display: "grid",
               gridTemplateColumns: "1fr 360px",
               gap: 32,
               alignItems: "start",
            }}>
            {/* ── LEFT COLUMN — Investigation ──────────────────────────── */}
            <div>
               {/* Snipped image card (replaces full PostCard) */}
               <div
                  style={{
                     background: "#fff",
                     border: "1.5px solid #e5e7eb",
                     borderRadius: 14,
                     overflow: "hidden",
                     marginBottom: 16,
                     boxShadow: "0 1px 6px rgba(0,0,0,0.05)",
                  }}>
                  <div
                     style={{
                        padding: "14px 16px 10px",
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        borderBottom: "1px solid #f3f4f6",
                     }}>
                     <Avatar
                        Icon={AV[post.avatarKey]?.Icon || UserCircle}
                        bg={AV[post.avatarKey]?.bg || "#ede9fe"}
                        color={AV[post.avatarKey]?.color || T.violet}
                        size={36}
                     />
                     <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#111827" }}>
                           {post.author}
                        </div>
                        <div
                           style={{
                              fontSize: 10,
                              color: T.gray,
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                           }}>
                           {post.date} <span style={{ color: "#d1d5db" }}>·</span>
                           <Search
                              size={9}
                              color={T.indigo}
                           />
                           <span style={{ color: T.indigo, fontWeight: 600 }}>via TruthLens</span>
                        </div>
                     </div>
                     <div
                        style={{
                           marginLeft: "auto",
                           display: "flex",
                           gap: 8,
                           alignItems: "center",
                        }}>
                        <span
                           style={{
                              fontSize: 11,
                              color: T.gray,
                              background: "#f3f4f6",
                              borderRadius: 6,
                              padding: "3px 8px",
                           }}>
                           Original post
                        </span>
                        <ExternalLink
                           size={14}
                           color={T.gray}
                           style={{ cursor: "pointer" }}
                        />
                     </div>
                  </div>
                  <ImgPlaceholder
                     label={`Snipped from ${post.source}`}
                     Icon={post.imageIcon || Image}
                  />
               </div>

               {/* Evidence Submit toggle */}
               <div style={{ marginBottom: 16 }}>
                  <button
                     onClick={() => setShowForm((v) => !v)}
                     style={{
                        width: "100%",
                        background: showForm ? "#eff6ff" : T.indigo,
                        color: showForm ? T.indigo : "#fff",
                        border: `1.5px solid ${showForm ? T.indigo : "transparent"}`,
                        borderRadius: showForm ? "10px 10px 0 0" : "10px",
                        padding: "13px",
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
                           padding: "20px",
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
                              Your weight: <strong style={{ color: T.green }}>×1.8</strong> (Trust
                              Score 82)
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

               {/* Tabs: Comments | Evidence Board */}
               <div
                  style={{
                     background: "#fff",
                     border: "1.5px solid #e5e7eb",
                     borderRadius: 14,
                     overflow: "hidden",
                  }}>
                  <div style={{ display: "flex", borderBottom: "1.5px solid #e5e7eb" }}>
                     {[
                        {
                           id: "comments",
                           Icon: MessageCircle,
                           label: `Comments (${post.comments})`,
                        },
                        {
                           id: "evidence",
                           Icon: Paperclip,
                           label: `Evidence Board (${post.evidence})`,
                        },
                     ].map(({ id, Icon: TI, label }) => (
                        <button
                           key={id}
                           onClick={() => setActiveTab(id)}
                           style={{
                              flex: 1,
                              padding: "14px 8px",
                              fontSize: 12,
                              fontWeight: 700,
                              background: activeTab === id ? "#fff" : "#f9fafb",
                              color: activeTab === id ? T.indigo : T.gray,
                              border: "none",
                              borderBottom:
                                 activeTab === id
                                    ? `2px solid ${T.indigo}`
                                    : "2px solid transparent",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              gap: 7,
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
                     <div style={{ padding: 20 }}>
                        <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
                           <Avatar
                              Icon={UserCircle}
                              bg="#ede9fe"
                              color={T.violet}
                              size={34}
                           />
                           <div
                              style={{
                                 flex: 1,
                                 background: "#f9fafb",
                                 border: "1.5px solid #e5e7eb",
                                 borderRadius: 20,
                                 padding: "10px 18px",
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
                        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
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
                                       size={34}
                                    />
                                    <div style={{ flex: 1 }}>
                                       <div
                                          style={{
                                             background: "#f9fafb",
                                             borderRadius: "0 14px 14px 14px",
                                             padding: "12px 16px",
                                          }}>
                                          <div
                                             style={{
                                                display: "flex",
                                                alignItems: "center",
                                                gap: 6,
                                                marginBottom: 5,
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
                                                      padding: "1px 6px",
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
                                                lineHeight: 1.65,
                                             }}>
                                             {c.t}
                                          </p>
                                       </div>
                                       <div
                                          style={{
                                             display: "flex",
                                             gap: 12,
                                             marginTop: 6,
                                             paddingLeft: 16,
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

                  {/* Evidence Board */}
                  {activeTab === "evidence" && (
                     <div
                        style={{ padding: 20, display: "flex", flexDirection: "column", gap: 12 }}>
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
                                 padding: "16px 18px",
                              }}>
                              <div
                                 style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    marginBottom: 10,
                                 }}>
                                 <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <Avatar
                                       Icon={UserCircle}
                                       bg="#ede9fe"
                                       color={T.violet}
                                       size={30}
                                    />
                                    <div>
                                       <div
                                          style={{
                                             fontSize: 12,
                                             fontWeight: 700,
                                             color: "#111827",
                                          }}>
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
                                          <strong style={{ color: tier(e.score) }}>
                                             {e.score}
                                          </strong>
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
                                    lineHeight: 1.65,
                                    margin: "0 0 12px",
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

            {/* ── RIGHT SIDEBAR ─────────────────────────────────────────── */}
            <div
               style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 16,
                  position: "sticky",
                  top: 64,
               }}>
               {/* Submitter card */}
               <div
                  style={{
                     background: "#fff",
                     border: "1.5px solid #e5e7eb",
                     borderRadius: 14,
                     padding: "20px",
                     boxShadow: "0 1px 6px rgba(0,0,0,0.05)",
                  }}>
                  <div
                     style={{
                        fontSize: 11,
                        fontWeight: 800,
                        color: T.gray,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        marginBottom: 14,
                     }}>
                     Posted by
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
                     <Avatar
                        Icon={AV.detective.Icon}
                        bg={AV.detective.bg}
                        color={AV.detective.color}
                        size={44}
                     />
                     <div>
                        <div style={{ fontSize: 14, fontWeight: 800, color: "#111827" }}>
                           @photocheck
                        </div>
                        <div
                           style={{
                              fontSize: 11,
                              color: T.gray,
                              marginTop: 2,
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                           }}>
                           <BadgeCheck
                              size={11}
                              color={T.green}
                           />
                           Trusted Contributor
                        </div>
                     </div>
                     <TrustGauge score={78} />
                  </div>
                  <div
                     style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr 1fr",
                        gap: 8,
                        textAlign: "center",
                     }}>
                     {[
                        ["142", "Scans"],
                        ["38", "Evidence"],
                        ["91%", "Accuracy"],
                     ].map(([val, lbl]) => (
                        <div
                           key={lbl}
                           style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 4px" }}>
                           <div style={{ fontSize: 14, fontWeight: 900, color: "#111827" }}>
                              {val}
                           </div>
                           <div style={{ fontSize: 9, color: T.gray, fontWeight: 600 }}>{lbl}</div>
                        </div>
                     ))}
                  </div>
               </div>

               {/* Trust Score mini-breakdown */}
               <div
                  style={{
                     background: "#fff",
                     border: "1.5px solid #e5e7eb",
                     borderRadius: 14,
                     padding: "20px",
                     boxShadow: "0 1px 6px rgba(0,0,0,0.05)",
                  }}>
                  <div
                     style={{
                        fontSize: 11,
                        fontWeight: 800,
                        color: T.gray,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        marginBottom: 14,
                     }}>
                     Community Trust Score
                  </div>
                  {[
                     { label: "Accuracy Rate", score: 91, color: T.green },
                     { label: "Evidence Quality", score: 74, color: T.amber },
                     { label: "Vote Balance", score: 67, color: T.amber },
                     { label: "Tenure Bonus", score: 82, color: T.indigo },
                  ].map(({ label, score, color }) => (
                     <div
                        key={label}
                        style={{ marginBottom: 12 }}>
                        <div
                           style={{
                              display: "flex",
                              justifyContent: "space-between",
                              fontSize: 11,
                              color: "#374151",
                              fontWeight: 600,
                              marginBottom: 5,
                           }}>
                           <span>{label}</span>
                           <span style={{ color, fontWeight: 800 }}>{score}</span>
                        </div>
                        <div style={{ height: 5, background: "#f3f4f6", borderRadius: 99 }}>
                           <div
                              style={{
                                 width: `${score}%`,
                                 height: "100%",
                                 background: color,
                                 borderRadius: 99,
                              }}
                           />
                        </div>
                     </div>
                  ))}
                  <a
                     style={{
                        fontSize: 11,
                        color: T.indigo,
                        fontWeight: 700,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                        marginTop: 4,
                     }}>
                     Full breakdown{" "}
                     <ArrowRight
                        size={11}
                        color={T.indigo}
                     />
                  </a>
               </div>

               {/* Related claims */}
               <div
                  style={{
                     background: "#fff",
                     border: "1.5px solid #e5e7eb",
                     borderRadius: 14,
                     padding: "20px",
                     boxShadow: "0 1px 6px rgba(0,0,0,0.05)",
                  }}>
                  <div
                     style={{
                        fontSize: 11,
                        fontWeight: 800,
                        color: T.gray,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        marginBottom: 14,
                     }}>
                     Related Claims
                  </div>
                  {[
                     {
                        text: '"Flooding photo from Thailand misused as 2023 Libya disaster"',
                        verdict: "fake",
                     },
                     {
                        text: '"Climate report data cherry-picked by viral post"',
                        verdict: "misleading",
                     },
                     {
                        text: '"Hurricane Ian aerial photo misidentified as recent event"',
                        verdict: "fake",
                     },
                  ].map((r, i) => (
                     <div
                        key={i}
                        style={{
                           display: "flex",
                           alignItems: "flex-start",
                           gap: 10,
                           padding: "10px 0",
                           borderBottom: i < 2 ? "1px solid #f3f4f6" : "none",
                           cursor: "pointer",
                        }}>
                        <VerdictBadge verdict={r.verdict} />
                        <p
                           style={{
                              fontSize: 11,
                              color: "#374151",
                              lineHeight: 1.5,
                              margin: 0,
                              fontWeight: 500,
                           }}>
                           {r.text}
                        </p>
                     </div>
                  ))}
               </div>

               {/* Report / flag actions */}
               <div
                  style={{
                     background: "#fff",
                     border: "1.5px solid #e5e7eb",
                     borderRadius: 14,
                     padding: "16px 20px",
                     display: "flex",
                     gap: 10,
                  }}>
                  <button
                     style={{
                        flex: 1,
                        padding: "9px",
                        background: "#fef2f2",
                        border: "1.5px solid #fecaca",
                        borderRadius: 8,
                        fontSize: 11,
                        fontWeight: 700,
                        color: "#991b1b",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 6,
                     }}>
                     <Flag
                        size={12}
                        strokeWidth={2.5}
                     />
                     Report
                  </button>
                  <button
                     style={{
                        flex: 1,
                        padding: "9px",
                        background: "#f9fafb",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 8,
                        fontSize: 11,
                        fontWeight: 700,
                        color: T.gray,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 6,
                     }}>
                     <ExternalLink
                        size={12}
                        strokeWidth={2}
                     />
                     Share
                  </button>
               </div>
            </div>
         </div>
         {/* end two-column body */}
      </div>
   );
};

// ─── View: Create Thread (from Extension) ────────────────────────────────────
const CreateThread = () => {
   const [category, setCategory] = useState("misleading");
   const [step, setStep] = useState(1); // 1 = form, 2 = preview confirm

   const categories = [
      { id: "misleading", Icon: AlertTriangle, label: "Misleading", color: T.amber },
      { id: "fake", Icon: XCircle, label: "Likely False", color: T.red },
      { id: "unverified", Icon: HelpCircle, label: "Unverified", color: T.gray },
      { id: "satire", Icon: Wand2, label: "Possible Satire", color: T.violet },
   ];
   const cat = categories.find((c) => c.id === category);

   return (
      <div style={{ background: "#ffffff", minHeight: "100%" }}>
         <AppNav activePage="feed" />

         {/* Sub-header */}
         <div
            style={{
               background: "#fff",
               borderBottom: `3px solid ${T.indigo}`,
               padding: "0 40px",
               height: 52,
               display: "flex",
               alignItems: "center",
               gap: 16,
               boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
            }}>
            <button
               style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: 700,
                  color: T.indigo,
                  padding: "6px 0",
               }}>
               <ArrowRight
                  size={14}
                  color={T.indigo}
                  style={{ transform: "rotate(180deg)" }}
               />
               Back to extension
            </button>
            <span style={{ color: "#e5e7eb", fontSize: 18 }}>›</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>
               Ask the Community
            </span>
            {/* Step indicator */}
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
               {["Review Claim", "Confirm & Post"].map((s, i) => (
                  <div
                     key={s}
                     style={{ display: "flex", alignItems: "center", gap: 6 }}>
                     <div
                        style={{
                           width: 22,
                           height: 22,
                           borderRadius: "50%",
                           background:
                              step > i + 1 ? T.green : step === i + 1 ? T.indigo : "#e5e7eb",
                           display: "flex",
                           alignItems: "center",
                           justifyContent: "center",
                        }}>
                        {step > i + 1 ? (
                           <CheckCircle2
                              size={13}
                              color="#fff"
                              strokeWidth={3}
                           />
                        ) : (
                           <span
                              style={{
                                 fontSize: 11,
                                 fontWeight: 800,
                                 color: step === i + 1 ? "#fff" : "#9ca3af",
                              }}>
                              {i + 1}
                           </span>
                        )}
                     </div>
                     <span
                        style={{
                           fontSize: 11,
                           fontWeight: 600,
                           color: step === i + 1 ? T.indigo : "#9ca3af",
                        }}>
                        {s}
                     </span>
                     {i < 1 && (
                        <ArrowRight
                           size={11}
                           color="#d1d5db"
                        />
                     )}
                  </div>
               ))}
            </div>
         </div>

         {/* Page intro banner — explains the extension context */}
         <div
            style={{
               background: `${T.indigo}08`,
               borderBottom: `1px solid ${T.indigo}20`,
               padding: "16px 40px",
               display: "flex",
               alignItems: "center",
               gap: 12,
            }}>
            <div
               style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  background: T.indigo,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
               }}>
               <ScanLine
                  size={18}
                  color="#fff"
                  strokeWidth={2}
               />
            </div>
            <div>
               <div style={{ fontSize: 13, fontWeight: 800, color: T.dark }}>
                  Claim snipped from <span style={{ color: T.indigo }}>twitter.com</span>
               </div>
               <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>
                  TruthLens found this content during your browsing session. Review and post it to
                  the community for investigation.
               </div>
            </div>
            <div
               style={{
                  marginLeft: "auto",
                  fontSize: 11,
                  color: T.gray,
                  background: "#f3f4f6",
                  borderRadius: 6,
                  padding: "4px 10px",
                  display: "flex",
                  alignItems: "center",
                  gap: 5,
               }}>
               <Clock
                  size={11}
                  color={T.gray}
               />
               Snipped 2 minutes ago
            </div>
         </div>

         {step === 1 && (
            <div
               style={{
                  maxWidth: 1100,
                  margin: "0 auto",
                  padding: "36px 40px 64px",
                  display: "grid",
                  gridTemplateColumns: "1fr 340px",
                  gap: 32,
                  alignItems: "start",
               }}>
               {/* ── LEFT: Form ─────────────────────────────────────────── */}
               <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  {/* Snipped content preview */}
                  <div
                     style={{
                        background: "#fff",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 14,
                        overflow: "hidden",
                        boxShadow: "0 1px 6px rgba(0,0,0,0.05)",
                     }}>
                     <div
                        style={{
                           padding: "12px 16px",
                           background: "#f9fafb",
                           borderBottom: "1px solid #f0f0f0",
                           display: "flex",
                           alignItems: "center",
                           justifyContent: "space-between",
                        }}>
                        <span
                           style={{
                              fontSize: 11,
                              fontWeight: 800,
                              color: T.gray,
                              letterSpacing: "0.08em",
                              textTransform: "uppercase",
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                           }}>
                           <Scissors
                              size={11}
                              color={T.gray}
                           />
                           Snipped Content
                        </span>
                        <button
                           style={{
                              fontSize: 11,
                              color: T.indigo,
                              fontWeight: 700,
                              background: "none",
                              border: "none",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                           }}>
                           <RefreshCw
                              size={11}
                              color={T.indigo}
                           />
                           Re-snip
                        </button>
                     </div>
                     <ImgPlaceholder
                        label="Snipped from twitter.com"
                        Icon={Globe}
                     />
                     <div
                        style={{
                           padding: "12px 16px",
                           borderTop: "1px solid #f0f0f0",
                           display: "flex",
                           alignItems: "center",
                           gap: 8,
                           fontSize: 11,
                           color: T.gray,
                        }}>
                        <Globe
                           size={11}
                           color={T.gray}
                        />
                        <span>
                           Source:{" "}
                           <strong style={{ color: "#374151" }}>
                              twitter.com/user/status/123456789
                           </strong>
                        </span>
                        <a
                           style={{
                              marginLeft: "auto",
                              color: T.indigo,
                              fontWeight: 600,
                              display: "flex",
                              alignItems: "center",
                              gap: 3,
                              cursor: "pointer",
                           }}>
                           <ExternalLink
                              size={10}
                              color={T.indigo}
                           />
                           Open original
                        </a>
                     </div>
                  </div>

                  {/* Claim text */}
                  <div>
                     <label
                        style={{
                           fontSize: 12,
                           fontWeight: 800,
                           color: "#374151",
                           display: "block",
                           marginBottom: 8,
                        }}>
                        Claim Text <span style={{ color: T.red }}>*</span>
                        <span
                           style={{ fontSize: 10, fontWeight: 500, color: T.gray, marginLeft: 8 }}>
                           Auto-extracted — edit if needed
                        </span>
                     </label>
                     <div
                        style={{
                           background: "#f9fafb",
                           border: `1.5px solid ${T.indigo}`,
                           borderRadius: 10,
                           padding: "14px 16px",
                           fontSize: 13,
                           color: "#374151",
                           lineHeight: 1.65,
                           minHeight: 90,
                           fontStyle: "italic",
                        }}>
                        "Shocking aerial photo shows the aftermath of the 2024 flooding in Valencia,
                        Spain."
                     </div>
                     <div
                        style={{
                           fontSize: 10,
                           color: T.gray,
                           marginTop: 5,
                           display: "flex",
                           alignItems: "center",
                           gap: 4,
                        }}>
                        <Info
                           size={10}
                           color={T.gray}
                        />
                        This is what the community will investigate. Make it as accurate as
                        possible.
                     </div>
                  </div>

                  {/* Source URL */}
                  <div>
                     <label
                        style={{
                           fontSize: 12,
                           fontWeight: 800,
                           color: "#374151",
                           display: "block",
                           marginBottom: 8,
                        }}>
                        Source URL <span style={{ color: T.red }}>*</span>
                        <span
                           style={{ fontSize: 10, fontWeight: 500, color: T.gray, marginLeft: 8 }}>
                           Auto-filled from your browser tab
                        </span>
                     </label>
                     <div
                        style={{
                           background: "#f9fafb",
                           border: "1.5px solid #e5e7eb",
                           borderBottom: `2px solid ${T.indigo}`,
                           borderRadius: "8px 8px 0 0",
                           padding: "12px 14px",
                           fontSize: 13,
                           color: "#374151",
                           display: "flex",
                           alignItems: "center",
                           gap: 8,
                        }}>
                        <Link
                           size={14}
                           color={T.indigo}
                        />
                        twitter.com/user/status/123456789
                     </div>
                  </div>

                  {/* Initial verdict category */}
                  <div>
                     <label
                        style={{
                           fontSize: 12,
                           fontWeight: 800,
                           color: "#374151",
                           display: "block",
                           marginBottom: 8,
                        }}>
                        Why are you flagging this?
                        <span
                           style={{ fontSize: 10, fontWeight: 500, color: T.gray, marginLeft: 8 }}>
                           AI suggestion: Misleading
                        </span>
                     </label>
                     <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                        {categories.map(({ id, Icon: CI, label, color }) => (
                           <button
                              key={id}
                              onClick={() => setCategory(id)}
                              style={{
                                 display: "flex",
                                 alignItems: "center",
                                 gap: 10,
                                 padding: "12px 16px",
                                 background: category === id ? `${color}12` : "#f9fafb",
                                 border: `1.5px solid ${category === id ? color : "#e5e7eb"}`,
                                 borderRadius: 10,
                                 cursor: "pointer",
                                 textAlign: "left",
                                 transition: "all 0.15s",
                              }}>
                              <div
                                 style={{
                                    width: 32,
                                    height: 32,
                                    borderRadius: 8,
                                    background: category === id ? `${color}20` : "#fff",
                                    border: `1px solid ${category === id ? color + "40" : "#e5e7eb"}`,
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    flexShrink: 0,
                                 }}>
                                 <CI
                                    size={15}
                                    color={category === id ? color : T.gray}
                                    strokeWidth={2}
                                 />
                              </div>
                              <div>
                                 <div
                                    style={{
                                       fontSize: 12,
                                       fontWeight: 700,
                                       color: category === id ? color : "#374151",
                                    }}>
                                    {label}
                                 </div>
                                 <div style={{ fontSize: 10, color: T.gray, marginTop: 1 }}>
                                    {id === "misleading" && "Missing context or partially true"}
                                    {id === "fake" && "Appears to be fabricated"}
                                    {id === "unverified" && "Can't confirm either way"}
                                    {id === "satire" && "Looks like parody content"}
                                 </div>
                              </div>
                              {category === id && (
                                 <CheckCircle2
                                    size={14}
                                    color={color}
                                    style={{ marginLeft: "auto" }}
                                 />
                              )}
                           </button>
                        ))}
                     </div>
                  </div>

                  {/* Additional context */}
                  <div>
                     <label
                        style={{
                           fontSize: 12,
                           fontWeight: 800,
                           color: "#374151",
                           display: "block",
                           marginBottom: 8,
                        }}>
                        Additional Context{" "}
                        <span style={{ fontSize: 10, fontWeight: 500, color: T.gray }}>
                           Optional
                        </span>
                     </label>
                     <div
                        style={{
                           background: "#f9fafb",
                           border: "1.5px solid #e5e7eb",
                           borderRadius: 10,
                           padding: "12px 16px",
                           fontSize: 12,
                           color: "#9ca3af",
                           minHeight: 80,
                           lineHeight: 1.65,
                        }}>
                        Add anything that might help the community investigate this claim…
                     </div>
                  </div>

                  {/* Submit row */}
                  <div style={{ display: "flex", gap: 12, paddingTop: 8 }}>
                     <button
                        style={{
                           flex: 1,
                           padding: "14px",
                           background: T.indigo,
                           color: "#fff",
                           border: "none",
                           borderRadius: 10,
                           fontSize: 14,
                           fontWeight: 800,
                           cursor: "pointer",
                           display: "flex",
                           alignItems: "center",
                           justifyContent: "center",
                           gap: 8,
                           letterSpacing: "0.02em",
                        }}
                        onClick={() => setStep(2)}>
                        <Users
                           size={16}
                           strokeWidth={2.5}
                        />
                        Preview & Post to Community
                        <ArrowRight
                           size={15}
                           strokeWidth={2.5}
                        />
                     </button>
                     <button
                        style={{
                           padding: "14px 20px",
                           background: "#f3f4f6",
                           color: T.gray,
                           border: "1.5px solid #e5e7eb",
                           borderRadius: 10,
                           fontSize: 13,
                           fontWeight: 700,
                           cursor: "pointer",
                        }}>
                        Save Draft
                     </button>
                  </div>
               </div>

               {/* ── RIGHT SIDEBAR ────────────────────────────────────── */}
               <div
                  style={{
                     display: "flex",
                     flexDirection: "column",
                     gap: 16,
                     position: "sticky",
                     top: 64,
                  }}>
                  {/* AI verdict summary */}
                  <div
                     style={{
                        background: "#fff",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 14,
                        overflow: "hidden",
                        boxShadow: "0 1px 6px rgba(0,0,0,0.05)",
                     }}>
                     <div
                        style={{
                           padding: "14px 16px",
                           background: `${T.amber}12`,
                           borderBottom: `1px solid ${T.amber}30`,
                           display: "flex",
                           alignItems: "center",
                           gap: 8,
                        }}>
                        <Sparkles
                           size={13}
                           color={T.amber}
                           strokeWidth={2.5}
                        />
                        <span
                           style={{
                              fontSize: 11,
                              fontWeight: 800,
                              color: T.amber,
                              letterSpacing: "0.06em",
                              textTransform: "uppercase",
                           }}>
                           AI Pre-Analysis
                        </span>
                     </div>
                     <div style={{ padding: "16px" }}>
                        <div
                           style={{
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              marginBottom: 14,
                           }}>
                           <VerdictBadge verdict="misleading" />
                           <span style={{ fontSize: 18, fontWeight: 900, color: T.amber }}>
                              47%
                           </span>
                        </div>
                        <div
                           style={{
                              height: 5,
                              background: "#f3f4f6",
                              borderRadius: 99,
                              marginBottom: 8,
                           }}>
                           <div
                              style={{
                                 width: "47%",
                                 height: "100%",
                                 background: T.amber,
                                 borderRadius: 99,
                              }}
                           />
                        </div>
                        <p
                           style={{
                              fontSize: 11,
                              color: T.gray,
                              lineHeight: 1.65,
                              margin: "0 0 12px",
                           }}>
                           Low AI confidence — the image metadata doesn't match the claimed
                           location. Human review strongly recommended.
                        </p>
                        <div
                           style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                              fontSize: 10,
                              color: T.gray,
                              background: "#f9fafb",
                              borderRadius: 7,
                              padding: "8px 10px",
                           }}>
                           <Info
                              size={11}
                              color={T.gray}
                           />
                           This verdict can change once the community submits evidence.
                        </div>
                     </div>
                  </div>

                  {/* Duplicate check */}
                  <div
                     style={{
                        background: "#fff",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 14,
                        padding: "16px",
                        boxShadow: "0 1px 6px rgba(0,0,0,0.05)",
                     }}>
                     <div
                        style={{
                           fontSize: 11,
                           fontWeight: 800,
                           color: T.gray,
                           letterSpacing: "0.08em",
                           textTransform: "uppercase",
                           marginBottom: 12,
                        }}>
                        Similar Threads
                     </div>
                     {[
                        {
                           text: '"Valencia flood photo misidentified"',
                           verdict: "fake",
                           threads: 3,
                        },
                        {
                           text: '"2019 SEA flood used in 2024 news coverage"',
                           verdict: "misleading",
                           threads: 1,
                        },
                     ].map((r, i) => (
                        <div
                           key={i}
                           style={{
                              display: "flex",
                              alignItems: "flex-start",
                              gap: 8,
                              padding: "9px 0",
                              borderBottom: i === 0 ? "1px solid #f3f4f6" : "none",
                           }}>
                           <VerdictBadge verdict={r.verdict} />
                           <div style={{ flex: 1 }}>
                              <p
                                 style={{
                                    fontSize: 11,
                                    color: "#374151",
                                    lineHeight: 1.4,
                                    margin: "0 0 3px",
                                    fontWeight: 500,
                                 }}>
                                 {r.text}
                              </p>
                              <span style={{ fontSize: 10, color: T.gray }}>
                                 {r.threads} existing thread{r.threads > 1 ? "s" : ""}
                              </span>
                           </div>
                           <a
                              style={{
                                 fontSize: 10,
                                 color: T.indigo,
                                 fontWeight: 700,
                                 cursor: "pointer",
                                 flexShrink: 0,
                              }}>
                              View
                           </a>
                        </div>
                     ))}
                     <div
                        style={{
                           marginTop: 10,
                           fontSize: 11,
                           color: T.gray,
                           display: "flex",
                           alignItems: "center",
                           gap: 5,
                           background: "#fffbeb",
                           borderRadius: 7,
                           padding: "8px 10px",
                           border: "1px solid #fde68a",
                        }}>
                        <AlertTriangle
                           size={11}
                           color={T.amber}
                        />
                        Consider linking to an existing thread instead of creating a duplicate.
                     </div>
                  </div>

                  {/* Community guidelines reminder */}
                  <div
                     style={{
                        background: "#f9fafb",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 14,
                        padding: "16px",
                     }}>
                     <div
                        style={{
                           fontSize: 11,
                           fontWeight: 800,
                           color: T.gray,
                           letterSpacing: "0.08em",
                           textTransform: "uppercase",
                           marginBottom: 10,
                        }}>
                        Before You Post
                     </div>
                     {[
                        "Only flag claims you genuinely believe need investigation",
                        "Don't post the same claim as an existing thread",
                        "You earn Trust Score when your flagged claims get verified",
                     ].map((tip, i) => (
                        <div
                           key={i}
                           style={{
                              display: "flex",
                              alignItems: "flex-start",
                              gap: 8,
                              marginBottom: 8,
                           }}>
                           <CheckCircle2
                              size={13}
                              color={T.green}
                              strokeWidth={2.5}
                              style={{ flexShrink: 0, marginTop: 1 }}
                           />
                           <span style={{ fontSize: 11, color: "#374151", lineHeight: 1.5 }}>
                              {tip}
                           </span>
                        </div>
                     ))}
                  </div>
               </div>
            </div>
         )}

         {/* ── Step 2: Preview & Confirm ──────────────────────────────── */}
         {step === 2 && (
            <div style={{ maxWidth: 720, margin: "0 auto", padding: "36px 40px 64px" }}>
               <div
                  style={{
                     background: `${T.indigo}08`,
                     border: `1.5px solid ${T.indigo}30`,
                     borderRadius: 12,
                     padding: "14px 20px",
                     marginBottom: 24,
                     display: "flex",
                     alignItems: "center",
                     gap: 10,
                     fontSize: 13,
                     color: T.indigo,
                     fontWeight: 600,
                  }}>
                  <Eye
                     size={15}
                     color={T.indigo}
                  />
                  This is how your thread will appear in the Community Feed. Confirm to post.
               </div>
               {/* Rendered PostCard preview */}
               <PostCard
                  post={{
                     id: 99,
                     verdict: "misleading",
                     avatarKey: "detective",
                     author: "@verifyme",
                     date: "Just now",
                     source: "Twitter / X",
                     imageIcon: Globe,
                     caption:
                        '"Shocking aerial photo shows the aftermath of the 2024 flooding in Valencia, Spain."',
                     confidence: 47,
                     comments: 0,
                     evidence: 0,
                     status: "Needs Evidence",
                  }}
               />
               <div style={{ display: "flex", gap: 12, marginTop: 20 }}>
                  <button
                     onClick={() => setStep(1)}
                     style={{
                        padding: "13px 20px",
                        background: "#f3f4f6",
                        color: T.gray,
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 10,
                        fontSize: 13,
                        fontWeight: 700,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 7,
                     }}>
                     <ArrowRight
                        size={14}
                        color={T.gray}
                        style={{ transform: "rotate(180deg)" }}
                     />
                     Edit
                  </button>
                  <button
                     style={{
                        flex: 1,
                        padding: "13px",
                        background: T.indigo,
                        color: "#fff",
                        border: "none",
                        borderRadius: 10,
                        fontSize: 14,
                        fontWeight: 800,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 8,
                     }}>
                     <Users
                        size={16}
                        strokeWidth={2.5}
                     />
                     Post to Community
                     <ArrowRight
                        size={15}
                        strokeWidth={2.5}
                     />
                  </button>
               </div>
            </div>
         )}
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

// ─── View: Settings Page ──────────────────────────────────────────────────────
const SettingsPage = () => {
   const [emailNotifs, setEmailNotifs] = useState(true);
   const [pushNotifs, setPushNotifs] = useState(true);
   const [evidenceAlerts, setEvidenceAlerts] = useState(true);
   const [autoScan, setAutoScan] = useState(false);
   const Toggle = ({ on, onToggle }) => (
      <div
         onClick={onToggle}
         style={{ cursor: "pointer" }}>
         {on ? (
            <ToggleRight
               size={28}
               color={T.indigo}
               strokeWidth={2}
            />
         ) : (
            <ToggleLeft
               size={28}
               color={T.gray}
               strokeWidth={2}
            />
         )}
      </div>
   );
   const Row = ({ label, sub, on, onToggle }) => (
      <div
         style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "14px 0",
            borderBottom: "1px solid #f3f4f6",
         }}>
         <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>{label}</div>
            {sub && <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>{sub}</div>}
         </div>
         <Toggle
            on={on}
            onToggle={onToggle}
         />
      </div>
   );
   const Section = ({ title, Icon: SI, children }) => (
      <div
         style={{
            background: "#fff",
            borderRadius: 12,
            border: "1.5px solid #e5e7eb",
            marginBottom: 20,
            overflow: "hidden",
         }}>
         <div
            style={{
               padding: "14px 20px",
               borderBottom: "1px solid #f3f4f6",
               display: "flex",
               alignItems: "center",
               gap: 8,
               background: "#fafafa",
            }}>
            <div
               style={{
                  width: 28,
                  height: 28,
                  borderRadius: 7,
                  background: T.indigo,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
               }}>
               <SI
                  size={14}
                  color="#fff"
                  strokeWidth={2}
               />
            </div>
            <span style={{ fontSize: 13, fontWeight: 800, color: "#111827" }}>{title}</span>
         </div>
         <div style={{ padding: "0 20px" }}>{children}</div>
      </div>
   );
   return (
      <div style={{ background: "#f1f5f9", minHeight: "100%" }}>
         <AppNav activePage="settings" />
         <div style={{ maxWidth: 720, margin: "0 auto", padding: "32px 24px 64px" }}>
            <div style={{ marginBottom: 24 }}>
               <div
                  style={{
                     fontSize: 22,
                     fontWeight: 900,
                     color: "#111827",
                     letterSpacing: "-0.02em",
                  }}>
                  Settings
               </div>
               <div style={{ fontSize: 13, color: T.gray, marginTop: 4 }}>
                  Manage your account preferences and extension behaviour.
               </div>
            </div>
            <Section
               title="Profile"
               Icon={UserCircle}>
               <div style={{ padding: "16px 0" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
                     <Avatar
                        Icon={UserCircle}
                        bg="#ddd6fe"
                        color={T.violet}
                        size={56}
                     />
                     <div>
                        <button
                           style={{
                              fontSize: 11,
                              fontWeight: 700,
                              color: T.indigo,
                              background: "#eff6ff",
                              border: "1.5px solid #c7d2fe",
                              borderRadius: 6,
                              padding: "5px 12px",
                              cursor: "pointer",
                           }}>
                           Change Avatar
                        </button>
                        <div style={{ fontSize: 10, color: T.gray, marginTop: 4 }}>
                           JPG, PNG or GIF · max 2MB
                        </div>
                     </div>
                  </div>
                  {[
                     { label: "Display Name", val: "@verifyme" },
                     { label: "Email Address", val: "user@email.com" },
                     { label: "Bio", val: "Passionate about media literacy..." },
                  ].map(({ label, val }) => (
                     <div
                        key={label}
                        style={{ marginBottom: 14 }}>
                        <div
                           style={{
                              fontSize: 10,
                              fontWeight: 700,
                              color: T.gray,
                              letterSpacing: "0.06em",
                              textTransform: "uppercase",
                              marginBottom: 4,
                           }}>
                           {label}
                        </div>
                        <div
                           style={{
                              border: "1.5px solid #e5e7eb",
                              borderRadius: 7,
                              padding: "8px 12px",
                              fontSize: 12,
                              color: "#374151",
                              background: "#fafafa",
                           }}>
                           {val}
                        </div>
                     </div>
                  ))}
                  <button
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        background: T.indigo,
                        color: "#fff",
                        border: "none",
                        borderRadius: 7,
                        padding: "8px 18px",
                        cursor: "pointer",
                        marginTop: 4,
                     }}>
                     Save Changes
                  </button>
               </div>
            </Section>
            <Section
               title="Notifications"
               Icon={Bell}>
               <Row
                  label="Email notifications"
                  sub="Receive digest emails for your scans and threads"
                  on={emailNotifs}
                  onToggle={() => setEmailNotifs((p) => !p)}
               />
               <Row
                  label="Push notifications"
                  sub="Browser push alerts for votes and replies"
                  on={pushNotifs}
                  onToggle={() => setPushNotifs((p) => !p)}
               />
               <Row
                  label="Evidence alerts"
                  sub="Notify me when new evidence is added to my threads"
                  on={evidenceAlerts}
                  onToggle={() => setEvidenceAlerts((p) => !p)}
               />
            </Section>
            <Section
               title="Extension"
               Icon={ScanLine}>
               <Row
                  label="Auto-scan on page load"
                  sub="Automatically scan claims when you open a new page"
                  on={autoScan}
                  onToggle={() => setAutoScan((p) => !p)}
               />
               <div
                  style={{
                     padding: "14px 0",
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "space-between",
                  }}>
                  <div>
                     <div style={{ fontSize: 13, fontWeight: 600, color: "#111827" }}>
                        Confidence threshold
                     </div>
                     <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>
                        Only show results above this confidence %
                     </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                     {[60, 70, 80, 90].map((v) => (
                        <button
                           key={v}
                           style={{
                              fontSize: 11,
                              fontWeight: 700,
                              padding: "4px 10px",
                              borderRadius: 6,
                              border: `1.5px solid ${v === 70 ? T.indigo : "#e5e7eb"}`,
                              background: v === 70 ? T.indigo : "#fff",
                              color: v === 70 ? "#fff" : T.gray,
                              cursor: "pointer",
                           }}>
                           {v}%
                        </button>
                     ))}
                  </div>
               </div>
            </Section>
            <Section
               title="Privacy & Security"
               Icon={Lock}>
               <Row
                  label="Public profile"
                  sub="Allow others to view your contributions and Trust Score"
                  on={true}
                  onToggle={() => {}}
               />
               <Row
                  label="Anonymous voting"
                  sub="Hide your username on evidence votes"
                  on={false}
                  onToggle={() => {}}
               />
               <div style={{ padding: "16px 0" }}>
                  <button
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: T.red,
                        background: "#fff5f5",
                        border: "1.5px solid #fecaca",
                        borderRadius: 7,
                        padding: "8px 16px",
                        cursor: "pointer",
                     }}>
                     Change Password
                  </button>
               </div>
            </Section>
            <Section
               title="Danger Zone"
               Icon={AlertOctagon}>
               <div style={{ padding: "16px 0", display: "flex", gap: 12, flexWrap: "wrap" }}>
                  <button
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: T.gray,
                        background: "#f3f4f6",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 7,
                        padding: "8px 16px",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                     }}>
                     <LogOut
                        size={13}
                        color={T.gray}
                     />
                     Log Out of All Devices
                  </button>
                  <button
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: T.red,
                        background: "#fff5f5",
                        border: "1.5px solid #fecaca",
                        borderRadius: 7,
                        padding: "8px 16px",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                     }}>
                     <Trash2
                        size={13}
                        color={T.red}
                     />{" "}
                     Delete Account
                  </button>
                  <button
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: T.gray,
                        background: "#f3f4f6",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 7,
                        padding: "8px 16px",
                        cursor: "pointer",
                     }}>
                     Export My Data
                  </button>
               </div>
            </Section>
         </div>
      </div>
   );
};

// ─── View: Notifications Panel ─────────────────────────────────────────────────
const NotificationsPage = () => {
   const [activeTab, setActiveTab] = useState("all");
   const tabs = [
      { id: "all", label: "All" },
      { id: "votes", label: "Votes" },
      { id: "evidence", label: "Evidence" },
      { id: "system", label: "System" },
   ];
   const notifs = [
      {
         id: 1,
         read: false,
         Icon: ThumbsUp,
         iconBg: "#d1fae5",
         iconColor: T.green,
         title: "Your evidence on 'Valencia flooding photo' received 12 upvotes",
         time: "2m ago",
         type: "votes",
      },
      {
         id: 2,
         read: false,
         Icon: Paperclip,
         iconBg: "#e0e7ff",
         iconColor: T.indigo,
         title: "New evidence submitted on your thread 'Vaccine efficacy chart'",
         time: "1h ago",
         type: "evidence",
      },
      {
         id: 3,
         read: false,
         Icon: CheckCircle2,
         iconBg: "#d1fae5",
         iconColor: T.green,
         title: "Thread you contributed to has been marked Verified",
         time: "3h ago",
         type: "system",
      },
      {
         id: 4,
         read: true,
         Icon: AlertTriangle,
         iconBg: "#fef3c7",
         iconColor: T.amber,
         title: "Claim you submitted was updated to Misleading by community vote",
         time: "5h ago",
         type: "system",
      },
      {
         id: 5,
         read: true,
         Icon: ThumbsUp,
         iconBg: "#d1fae5",
         iconColor: T.green,
         title: "Your comment on 'Senator healthcare vote' received 5 likes",
         time: "1d ago",
         type: "votes",
      },
      {
         id: 6,
         read: true,
         Icon: Paperclip,
         iconBg: "#e0e7ff",
         iconColor: T.indigo,
         title: "@factchecker added evidence to a thread you're following",
         time: "2d ago",
         type: "evidence",
      },
      {
         id: 7,
         read: true,
         Icon: BadgeCheck,
         iconBg: "#ede9fe",
         iconColor: T.violet,
         title: "Your Trust Score increased to 82 — you've unlocked Trusted Contributor status",
         time: "3d ago",
         type: "system",
      },
   ];
   const filtered = activeTab === "all" ? notifs : notifs.filter((n) => n.type === activeTab);
   return (
      <div style={{ background: "#f1f5f9", minHeight: "100%" }}>
         <AppNav activePage="notifications" />
         <div style={{ maxWidth: 680, margin: "0 auto", padding: "32px 24px 64px" }}>
            <div
               style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 20,
               }}>
               <div>
                  <div
                     style={{
                        fontSize: 22,
                        fontWeight: 900,
                        color: "#111827",
                        letterSpacing: "-0.02em",
                     }}>
                     Notifications
                  </div>
                  <div style={{ fontSize: 13, color: T.gray, marginTop: 2 }}>3 unread</div>
               </div>
               <button
                  style={{
                     fontSize: 11,
                     fontWeight: 700,
                     color: T.indigo,
                     background: "transparent",
                     border: "none",
                     cursor: "pointer",
                     display: "flex",
                     alignItems: "center",
                     gap: 5,
                  }}>
                  <Check
                     size={13}
                     color={T.indigo}
                  />{" "}
                  Mark all read
               </button>
            </div>
            {/* Tabs */}
            <div
               style={{
                  display: "flex",
                  gap: 4,
                  background: "#fff",
                  borderRadius: 10,
                  padding: 4,
                  border: "1.5px solid #e5e7eb",
                  marginBottom: 20,
               }}>
               {tabs.map((t) => (
                  <button
                     key={t.id}
                     onClick={() => setActiveTab(t.id)}
                     style={{
                        flex: 1,
                        padding: "7px 0",
                        fontSize: 11,
                        fontWeight: 700,
                        borderRadius: 7,
                        border: "none",
                        background: activeTab === t.id ? T.indigo : "transparent",
                        color: activeTab === t.id ? "#fff" : T.gray,
                        cursor: "pointer",
                        transition: "all 0.15s",
                     }}>
                     {t.label}
                  </button>
               ))}
            </div>
            {/* List */}
            <div
               style={{
                  background: "#fff",
                  borderRadius: 12,
                  border: "1.5px solid #e5e7eb",
                  overflow: "hidden",
               }}>
               {filtered.map((n, i) => (
                  <div
                     key={n.id}
                     style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 14,
                        padding: "14px 18px",
                        borderBottom: i < filtered.length - 1 ? "1px solid #f3f4f6" : "none",
                        background: n.read ? "#fff" : "#f5f3ff",
                        cursor: "pointer",
                     }}>
                     <div
                        style={{
                           width: 38,
                           height: 38,
                           borderRadius: "50%",
                           background: n.iconBg,
                           display: "flex",
                           alignItems: "center",
                           justifyContent: "center",
                           flexShrink: 0,
                        }}>
                        <n.Icon
                           size={17}
                           color={n.iconColor}
                           strokeWidth={2}
                        />
                     </div>
                     <div style={{ flex: 1 }}>
                        <div
                           style={{
                              fontSize: 12,
                              color: "#1f2937",
                              lineHeight: 1.5,
                              fontWeight: n.read ? 400 : 600,
                           }}>
                           {n.title}
                        </div>
                        <div
                           style={{
                              fontSize: 10,
                              color: T.gray,
                              marginTop: 4,
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                           }}>
                           <Clock
                              size={9}
                              color={T.gray}
                           />{" "}
                           {n.time}
                        </div>
                     </div>
                     {!n.read && (
                        <div
                           style={{
                              width: 8,
                              height: 8,
                              borderRadius: "50%",
                              background: T.indigo,
                              flexShrink: 0,
                              marginTop: 4,
                           }}
                        />
                     )}
                  </div>
               ))}
            </div>
         </div>
      </div>
   );
};

// ─── View: User Profile Page (Public) ─────────────────────────────────────────
const UserProfilePage = () => {
   const [activeTab, setActiveTab] = useState("evidence");
   const tabs = [
      { id: "evidence", label: "Evidence Submitted" },
      { id: "threads", label: "Threads Started" },
      { id: "comments", label: "Comments" },
   ];
   const evidence = [
      {
         title: "CDC report confirms no link between 5G and health issues",
         thread: "5G towers cause cancer",
         verdict: "fake",
         votes: 34,
         date: "Jun 12",
      },
      {
         title: "Reuters fact-check: unemployment figures are accurate per BLS data",
         thread: "Unemployment at 50-year low",
         verdict: "verified",
         votes: 28,
         date: "Jun 10",
      },
      {
         title: "PubMed study contradicts mask efficacy claim — methodology flawed",
         thread: "Masks ineffective against COVID",
         verdict: "misleading",
         votes: 19,
         date: "Jun 8",
      },
   ];
   return (
      <div style={{ background: "#f1f5f9", minHeight: "100%" }}>
         <AppNav activePage="feed" />
         {/* Breadcrumb */}
         <div
            style={{
               background: "#fff",
               borderBottom: "1px solid #e5e7eb",
               padding: "10px 32px",
               display: "flex",
               alignItems: "center",
               gap: 6,
            }}>
            <Globe
               size={12}
               color={T.gray}
            />
            <span style={{ fontSize: 11, color: T.gray, cursor: "pointer" }}>Community Feed</span>
            <ChevronRight
               size={11}
               color="#d1d5db"
            />
            <span style={{ fontSize: 11, color: "#374151", fontWeight: 600 }}>@factchecker_ph</span>
         </div>
         <div style={{ maxWidth: 820, margin: "0 auto", padding: "28px 24px 64px" }}>
            {/* Profile Header */}
            <div
               style={{
                  background: "#fff",
                  borderRadius: 14,
                  border: "1.5px solid #e5e7eb",
                  padding: "28px 28px 20px",
                  marginBottom: 20,
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 20,
               }}>
               <Avatar
                  Icon={Eye}
                  bg="#fce7f3"
                  color="#be185d"
                  size={72}
               />
               <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                     <div style={{ fontSize: 20, fontWeight: 900, color: "#111827" }}>
                        @factchecker_ph
                     </div>
                     <BadgeCheck
                        size={18}
                        color={T.green}
                     />
                  </div>
                  <div
                     style={{
                        fontSize: 12,
                        color: T.gray,
                        marginBottom: 8,
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                     }}>
                     <Landmark
                        size={11}
                        color={T.gray}
                     />{" "}
                     Senior Fact-Checker · Joined March 2023
                  </div>
                  <div style={{ fontSize: 12, color: "#374151", lineHeight: 1.6, maxWidth: 480 }}>
                     Independent media researcher focused on Philippine political misinformation. 3+
                     years verifying viral claims across social platforms.
                  </div>
                  {/* Stats row */}
                  <div style={{ display: "flex", gap: 24, marginTop: 16 }}>
                     {[
                        { label: "Trust Score", val: "91", color: T.green },
                        { label: "Evidence", val: "147" },
                        { label: "Accuracy", val: "94%", color: T.green },
                        { label: "Votes Received", val: "1.2k" },
                     ].map(({ label, val, color }) => (
                        <div key={label}>
                           <div
                              style={{ fontSize: 18, fontWeight: 900, color: color || "#111827" }}>
                              {val}
                           </div>
                           <div
                              style={{
                                 fontSize: 9,
                                 color: T.gray,
                                 fontWeight: 700,
                                 letterSpacing: "0.06em",
                                 textTransform: "uppercase",
                              }}>
                              {label}
                           </div>
                        </div>
                     ))}
                  </div>
               </div>
               <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <button
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        background: T.indigo,
                        color: "#fff",
                        border: "none",
                        borderRadius: 8,
                        padding: "9px 20px",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                     }}>
                     <UserCheck
                        size={13}
                        color="#fff"
                     />{" "}
                     Follow
                  </button>
                  <button
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        background: "#fff",
                        color: T.gray,
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 8,
                        padding: "9px 20px",
                        cursor: "pointer",
                     }}>
                     Message
                  </button>
               </div>
            </div>
            {/* Trust Score visual */}
            <div
               style={{
                  background: "#fff",
                  borderRadius: 14,
                  border: "1.5px solid #e5e7eb",
                  padding: "20px 24px",
                  marginBottom: 20,
                  display: "flex",
                  alignItems: "center",
                  gap: 24,
               }}>
               <TrustGauge score={91} />
               <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 800, color: "#111827", marginBottom: 8 }}>
                     Trust Score Breakdown
                  </div>
                  {[
                     { label: "Evidence Accuracy", val: 94 },
                     { label: "Community Upvotes", val: 88 },
                     { label: "Submission Volume", val: 92 },
                  ].map(({ label, val }) => (
                     <div
                        key={label}
                        style={{ marginBottom: 8 }}>
                        <div
                           style={{
                              display: "flex",
                              justifyContent: "space-between",
                              marginBottom: 3,
                           }}>
                           <span style={{ fontSize: 11, color: "#374151", fontWeight: 600 }}>
                              {label}
                           </span>
                           <span style={{ fontSize: 11, color: T.green, fontWeight: 800 }}>
                              {val}%
                           </span>
                        </div>
                        <div style={{ height: 5, background: "#e5e7eb", borderRadius: 99 }}>
                           <div
                              style={{
                                 height: "100%",
                                 width: `${val}%`,
                                 background: T.green,
                                 borderRadius: 99,
                              }}
                           />
                        </div>
                     </div>
                  ))}
               </div>
            </div>
            {/* Tabs */}
            <div style={{ display: "flex", borderBottom: "2px solid #e5e7eb", marginBottom: 16 }}>
               {tabs.map((t) => (
                  <button
                     key={t.id}
                     onClick={() => setActiveTab(t.id)}
                     style={{
                        padding: "10px 18px",
                        fontSize: 12,
                        fontWeight: 700,
                        background: "transparent",
                        border: "none",
                        borderBottom: `2px solid ${activeTab === t.id ? T.indigo : "transparent"}`,
                        marginBottom: -2,
                        color: activeTab === t.id ? T.indigo : T.gray,
                        cursor: "pointer",
                     }}>
                     {t.label}
                  </button>
               ))}
            </div>
            {/* Evidence list */}
            {activeTab === "evidence" && (
               <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {evidence.map((e, i) => (
                     <div
                        key={i}
                        style={{
                           background: "#fff",
                           borderRadius: 10,
                           border: "1.5px solid #e5e7eb",
                           padding: "14px 18px",
                           borderLeft: `4px solid ${e.verdict === "verified" ? T.green : e.verdict === "fake" ? T.red : T.amber}`,
                        }}>
                        <div
                           style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "flex-start",
                           }}>
                           <div style={{ flex: 1 }}>
                              <div
                                 style={{
                                    fontSize: 13,
                                    fontWeight: 700,
                                    color: "#111827",
                                    marginBottom: 4,
                                 }}>
                                 {e.title}
                              </div>
                              <div
                                 style={{
                                    fontSize: 11,
                                    color: T.gray,
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 4,
                                 }}>
                                 <Paperclip
                                    size={10}
                                    color={T.gray}
                                 />{" "}
                                 On thread:{" "}
                                 <span style={{ color: T.indigo, fontWeight: 600 }}>
                                    "{e.thread}"
                                 </span>
                              </div>
                           </div>
                           <div
                              style={{
                                 display: "flex",
                                 alignItems: "center",
                                 gap: 10,
                                 flexShrink: 0,
                              }}>
                              <VerdictBadge verdict={e.verdict} />
                              <span
                                 style={{
                                    fontSize: 11,
                                    color: T.gray,
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 3,
                                 }}>
                                 <ThumbsUp
                                    size={11}
                                    color={T.gray}
                                 />{" "}
                                 {e.votes}
                              </span>
                           </div>
                        </div>
                     </div>
                  ))}
               </div>
            )}
            {(activeTab === "threads" || activeTab === "comments") && (
               <div
                  style={{
                     background: "#fff",
                     borderRadius: 10,
                     border: "1.5px solid #e5e7eb",
                     padding: "40px 24px",
                     textAlign: "center",
                  }}>
                  <div style={{ fontSize: 13, color: T.gray }}>No {activeTab} yet.</div>
               </div>
            )}
         </div>
      </div>
   );
};

// ─── View: Extension Minimized / Dismissed States ─────────────────────────────
const ExtMinimizedStates = () => {
   const MockPage = ({ children, label }) => (
      <div style={{ flex: 1 }}>
         <SLabel>{label}</SLabel>
         <div
            style={{
               background: "#f8fafc",
               border: "1.5px solid #e5e7eb",
               borderRadius: 10,
               overflow: "hidden",
               minHeight: 360,
               position: "relative",
            }}>
            {/* Fake webpage content */}
            <div style={{ padding: 20 }}>
               <div
                  style={{
                     height: 14,
                     background: "#e5e7eb",
                     borderRadius: 4,
                     width: "70%",
                     marginBottom: 10,
                  }}
               />
               <div
                  style={{
                     height: 10,
                     background: "#e5e7eb",
                     borderRadius: 4,
                     width: "90%",
                     marginBottom: 7,
                  }}
               />
               <div
                  style={{
                     height: 10,
                     background: "#e5e7eb",
                     borderRadius: 4,
                     width: "80%",
                     marginBottom: 7,
                  }}
               />
               <div
                  style={{
                     height: 10,
                     background: "#e5e7eb",
                     borderRadius: 4,
                     width: "60%",
                     marginBottom: 16,
                  }}
               />
               <div
                  style={{ height: 80, background: "#e5e7eb", borderRadius: 6, marginBottom: 12 }}
               />
               <div
                  style={{
                     height: 10,
                     background: "#e5e7eb",
                     borderRadius: 4,
                     width: "85%",
                     marginBottom: 7,
                  }}
               />
               <div
                  style={{
                     height: 10,
                     background: "#e5e7eb",
                     borderRadius: 4,
                     width: "70%",
                     marginBottom: 7,
                  }}
               />
            </div>
            {children}
         </div>
      </div>
   );
   return (
      <div>
         <SLabel>Extension States on Host Webpages</SLabel>
         <div style={{ display: "flex", gap: 24, alignItems: "flex-start", flexWrap: "wrap" }}>
            {/* Minimized pill */}
            <MockPage label="Minimized Pill State">
               <div
                  style={{
                     position: "absolute",
                     bottom: 16,
                     right: 16,
                     display: "flex",
                     alignItems: "center",
                     gap: 8,
                     background: T.dark,
                     borderRadius: 99,
                     padding: "7px 14px 7px 10px",
                     boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
                     cursor: "pointer",
                  }}>
                  <Logo
                     size={11}
                     bg={T.indigo}
                  />
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#fff" }}>TruthLens</span>
                  <div style={{ width: 1, height: 14, background: "rgba(255,255,255,0.2)" }} />
                  <VerdictBadge verdict="fake" />
                  <ChevronUp
                     size={13}
                     color="rgba(255,255,255,0.6)"
                  />
               </div>
               <div
                  style={{
                     position: "absolute",
                     bottom: 56,
                     right: 16,
                     fontSize: 10,
                     color: T.gray,
                     background: "#fff",
                     padding: "4px 8px",
                     borderRadius: 5,
                     border: "1px solid #e5e7eb",
                  }}>
                  Click pill to re-expand result
               </div>
            </MockPage>
            {/* Dismissed toast */}
            <MockPage label="Dismissed / Toast State">
               <div
                  style={{
                     position: "absolute",
                     top: 16,
                     right: 16,
                     display: "flex",
                     alignItems: "center",
                     gap: 10,
                     background: "#fff",
                     borderRadius: 10,
                     padding: "10px 14px",
                     boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
                     border: "1px solid #e5e7eb",
                     maxWidth: 240,
                  }}>
                  <div
                     style={{
                        width: 28,
                        height: 28,
                        borderRadius: 7,
                        background: "#fee2e2",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                     }}>
                     <XCircle
                        size={14}
                        color={T.red}
                        strokeWidth={2}
                     />
                  </div>
                  <div style={{ flex: 1 }}>
                     <div style={{ fontSize: 11, fontWeight: 700, color: "#111827" }}>
                        Claim flagged as Fake
                     </div>
                     <div
                        style={{
                           fontSize: 10,
                           color: T.indigo,
                           fontWeight: 600,
                           cursor: "pointer",
                           marginTop: 1,
                        }}>
                        View full analysis →
                     </div>
                  </div>
                  <X
                     size={13}
                     color={T.gray}
                     style={{ cursor: "pointer", flexShrink: 0 }}
                  />
               </div>
            </MockPage>
            {/* Scanning indicator */}
            <MockPage label="Passive Scan Indicator">
               <div
                  style={{
                     position: "absolute",
                     bottom: 16,
                     right: 16,
                     display: "flex",
                     alignItems: "center",
                     gap: 7,
                     background: "rgba(79,70,229,0.12)",
                     border: `1.5px solid rgba(79,70,229,0.3)`,
                     borderRadius: 99,
                     padding: "6px 12px",
                  }}>
                  <div
                     style={{
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        background: T.indigo,
                        animation: "pulse 1.5s infinite",
                     }}
                  />
                  <span style={{ fontSize: 10, fontWeight: 700, color: T.indigo }}>
                     Scanning page…
                  </span>
               </div>
            </MockPage>
         </div>
         {/* Annotations */}
         <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 24 }}>
            <Ann
               title="Component States"
               BoxIcon={Layers}
               color={T.indigo}
               items={[
                  "Minimized Pill — verdict badge visible, click to re-expand <ResultCard>",
                  "Dismissed Toast — top-right, auto-hides after 5s, 'View' deep-links to dashboard",
                  "Passive Scan Indicator — shown while background analysis is running",
                  "Each state is a separate React portal mounted on document.body",
               ]}
            />
            <Ann
               title="UX / Dev Notes"
               BoxIcon={Braces}
               color={T.violet}
               items={[
                  "Pill uses position:fixed bottom-right, z-index:2147483647 (max)",
                  "Toast auto-dismiss: setTimeout 5000ms, clearTimeout on hover",
                  "Minimized state persists in chrome.storage.local until page reload",
                  "Pill verdict color matches the full result card border — visual consistency",
               ]}
            />
         </div>
      </div>
   );
};

// ─── View: Trust Score Breakdown Modal ────────────────────────────────────────
const TrustBreakdown = () => {
   const factors = [
      {
         label: "Evidence Accuracy Rate",
         desc: "% of your evidence that matched community consensus",
         val: 87,
         weight: 40,
         color: T.green,
      },
      {
         label: "Community Upvotes",
         desc: "Net upvotes received on evidence submissions",
         val: 74,
         weight: 30,
         color: T.indigo,
      },
      {
         label: "Submission Volume",
         desc: "Consistency of contributions over time",
         val: 82,
         weight: 20,
         color: T.amber,
      },
      {
         label: "Account Age & Consistency",
         desc: "Tenure and submission regularity",
         val: 90,
         weight: 10,
         color: T.violet,
      },
   ];
   const weighted = Math.round(factors.reduce((acc, f) => acc + (f.val * f.weight) / 100, 0));
   return (
      <div
         style={{
            display: "grid",
            gridTemplateColumns: "1fr 380px",
            gap: 28,
            alignItems: "start",
         }}>
         {/* Dashboard bg preview */}
         <div>
            <SLabel>Dashboard — Trust Score section (modal trigger)</SLabel>
            <div
               style={{
                  background: "#fff",
                  borderRadius: 12,
                  border: "1.5px solid #e5e7eb",
                  padding: "20px 24px",
                  opacity: 0.4,
                  filter: "blur(1px)",
                  marginBottom: 0,
               }}>
               <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                  <TrustGauge score={82} />
                  <div>
                     <div style={{ fontSize: 16, fontWeight: 900, color: "#111827" }}>
                        Your Trust Score
                     </div>
                     <div style={{ fontSize: 11, color: T.gray, marginTop: 2 }}>
                        Based on your community contributions
                     </div>
                     <button
                        style={{
                           marginTop: 8,
                           fontSize: 10,
                           fontWeight: 700,
                           color: T.indigo,
                           background: "#eff6ff",
                           border: "1.5px solid #c7d2fe",
                           borderRadius: 6,
                           padding: "4px 10px",
                           cursor: "pointer",
                           display: "flex",
                           alignItems: "center",
                           gap: 4,
                        }}>
                        <Info
                           size={10}
                           color={T.indigo}
                        />{" "}
                        How is this calculated?
                     </button>
                  </div>
               </div>
            </div>
         </div>
         {/* Modal */}
         <div>
            <SLabel>Trust Score Breakdown Modal</SLabel>
            <div
               style={{
                  background: "#fff",
                  borderRadius: 14,
                  border: "1.5px solid #e5e7eb",
                  boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
                  overflow: "hidden",
               }}>
               {/* Modal header */}
               <div
                  style={{
                     background: `linear-gradient(135deg,${T.dark},#2d2a6e)`,
                     padding: "20px 20px 16px",
                  }}>
                  <div
                     style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                     }}>
                     <div>
                        <div
                           style={{
                              fontSize: 13,
                              fontWeight: 800,
                              color: "rgba(255,255,255,0.6)",
                              letterSpacing: "0.08em",
                              textTransform: "uppercase",
                           }}>
                           Trust Score
                        </div>
                        <div
                           style={{
                              fontSize: 32,
                              fontWeight: 900,
                              color: "#fff",
                              letterSpacing: "-0.02em",
                           }}>
                           {weighted}
                        </div>
                     </div>
                     <TrustGauge score={weighted} />
                  </div>
                  <div style={{ fontSize: 11, color: "rgba(255,255,255,0.55)", marginTop: 4 }}>
                     Weighted composite of 4 contribution factors
                  </div>
               </div>
               {/* Factors */}
               <div style={{ padding: "16px 20px" }}>
                  {factors.map((f, i) => (
                     <div
                        key={i}
                        style={{ marginBottom: 16 }}>
                        <div
                           style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              marginBottom: 4,
                           }}>
                           <div>
                              <div style={{ fontSize: 12, fontWeight: 700, color: "#111827" }}>
                                 {f.label}
                              </div>
                              <div style={{ fontSize: 10, color: T.gray }}>{f.desc}</div>
                           </div>
                           <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 12 }}>
                              <div style={{ fontSize: 16, fontWeight: 900, color: f.color }}>
                                 {f.val}
                              </div>
                              <div style={{ fontSize: 9, color: T.gray, fontWeight: 700 }}>
                                 ×{f.weight}% weight
                              </div>
                           </div>
                        </div>
                        <div style={{ height: 6, background: "#f3f4f6", borderRadius: 99 }}>
                           <div
                              style={{
                                 height: "100%",
                                 width: `${f.val}%`,
                                 background: f.color,
                                 borderRadius: 99,
                              }}
                           />
                        </div>
                     </div>
                  ))}
               </div>
               {/* Footer */}
               <div
                  style={{
                     padding: "12px 20px",
                     background: "#f9fafb",
                     borderTop: "1px solid #f3f4f6",
                     display: "flex",
                     justifyContent: "space-between",
                     alignItems: "center",
                  }}>
                  <div style={{ fontSize: 10, color: T.gray }}>
                     Updated daily · Score affects voting weight
                  </div>
                  <button
                     style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: "#fff",
                        background: T.indigo,
                        border: "none",
                        borderRadius: 7,
                        padding: "6px 14px",
                        cursor: "pointer",
                     }}>
                     See History
                  </button>
               </div>
            </div>
         </div>
         {/* Annotations */}
         <div
            style={{
               gridColumn: "1 / -1",
               display: "grid",
               gridTemplateColumns: "1fr 1fr",
               gap: 16,
               marginTop: 8,
            }}>
            <Ann
               title="Component Structure"
               BoxIcon={Braces}
               color={T.indigo}
               items={[
                  "<TrustScoreModal> — portal overlay, triggered by 'How is this calculated?' button",
                  "Modal header: dark gradient matches sidebar/AppNav brand colour",
                  "4 <FactorBar> rows: label + description + score + weight label + progress bar",
                  "Footer: update cadence note + 'See History' deep-link to score history page",
               ]}
            />
            <Ann
               title="UX Notes"
               BoxIcon={Palette}
               color={T.violet}
               items={[
                  "Blurred/dimmed dashboard behind modal signals context without leaving page",
                  "Each factor colour maps to design tokens: green=accuracy, indigo=votes, amber=volume",
                  "Weight labels (×40%) make the formula transparent — builds user trust in the system",
                  "'See History' links to a future chart view showing score trend over time",
               ]}
            />
         </div>
      </div>
   );
};

// ─── View: Empty & Loading States ─────────────────────────────────────────────
const EmptyStates = () => {
   const EmptyCard = ({ Icon: EI, iconBg, iconColor, title, sub, cta, ctaColor = T.indigo }) => (
      <div
         style={{
            background: "#fff",
            border: "1.5px solid #e5e7eb",
            borderRadius: 12,
            padding: "32px 24px",
            textAlign: "center",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12,
         }}>
         <div
            style={{
               width: 56,
               height: 56,
               borderRadius: 14,
               background: iconBg,
               display: "flex",
               alignItems: "center",
               justifyContent: "center",
            }}>
            <EI
               size={26}
               color={iconColor}
               strokeWidth={1.5}
            />
         </div>
         <div style={{ fontSize: 14, fontWeight: 800, color: "#111827" }}>{title}</div>
         <div style={{ fontSize: 11, color: T.gray, lineHeight: 1.6, maxWidth: 200 }}>{sub}</div>
         <button
            style={{
               fontSize: 11,
               fontWeight: 700,
               color: "#fff",
               background: ctaColor,
               border: "none",
               borderRadius: 7,
               padding: "7px 16px",
               cursor: "pointer",
               marginTop: 4,
            }}>
            {cta}
         </button>
      </div>
   );
   const SkeletonLine = ({ w = "100%", h = 10 }) => (
      <div
         style={{
            height: h,
            background: "linear-gradient(90deg,#f3f4f6 25%,#e5e7eb 50%,#f3f4f6 75%)",
            backgroundSize: "200% 100%",
            borderRadius: 4,
            width: w,
         }}
      />
   );
   return (
      <div>
         <SLabel>Empty States</SLabel>
         <div
            style={{
               display: "grid",
               gridTemplateColumns: "repeat(4,1fr)",
               gap: 16,
               marginBottom: 32,
            }}>
            <EmptyCard
               Icon={Globe}
               iconBg="#e0e7ff"
               iconColor={T.indigo}
               title="No posts yet"
               sub="Be the first to flag a claim and start a community thread."
               cta="Flag a Claim"
            />
            <EmptyCard
               Icon={ScanLine}
               iconBg="#d1fae5"
               iconColor={T.green}
               title="No scans yet"
               sub="Install the extension and snip your first suspicious claim."
               cta="Get the Extension"
               ctaColor={T.green}
            />
            <EmptyCard
               Icon={Paperclip}
               iconBg="#fef3c7"
               iconColor={T.amber}
               title="No evidence yet"
               sub="Be the first to submit a source and earn Trust Score points."
               cta="Add Evidence"
               ctaColor={T.amber}
            />
            <EmptyCard
               Icon={Bell}
               iconBg="#f3f4f6"
               iconColor={T.gray}
               title="All caught up"
               sub="You have no new notifications. Check back after contributing."
               cta="Browse Feed"
               ctaColor={T.gray}
            />
         </div>
         <SLabel>Loading / Skeleton States</SLabel>
         <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {/* PostCard skeleton */}
            <div>
               <div
                  style={{
                     fontSize: 10,
                     fontWeight: 700,
                     color: T.gray,
                     marginBottom: 8,
                     letterSpacing: "0.06em",
                     textTransform: "uppercase",
                  }}>
                  PostCard Skeleton
               </div>
               <div
                  style={{
                     background: "#fff",
                     borderRadius: 14,
                     border: "1.5px solid #e5e7eb",
                     overflow: "hidden",
                     padding: 0,
                  }}>
                  <div
                     style={{
                        padding: "14px 16px",
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                     }}>
                     <div
                        style={{
                           width: 38,
                           height: 38,
                           borderRadius: "50%",
                           background: "#f3f4f6",
                        }}
                     />
                     <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
                        <SkeletonLine
                           w="40%"
                           h={11}
                        />
                        <SkeletonLine
                           w="25%"
                           h={8}
                        />
                     </div>
                  </div>
                  <div
                     style={{
                        padding: "0 16px 12px",
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                     }}>
                     <SkeletonLine w="90%" />
                     <SkeletonLine w="75%" />
                  </div>
                  <div style={{ height: 160, background: "#f3f4f6" }} />
                  <div style={{ padding: "12px 16px", display: "flex", gap: 8 }}>
                     <SkeletonLine
                        w="30%"
                        h={28}
                     />
                     <SkeletonLine
                        w="30%"
                        h={28}
                     />
                     <SkeletonLine
                        w="30%"
                        h={28}
                     />
                  </div>
               </div>
            </div>
            {/* Thread evidence skeleton */}
            <div>
               <div
                  style={{
                     fontSize: 10,
                     fontWeight: 700,
                     color: T.gray,
                     marginBottom: 8,
                     letterSpacing: "0.06em",
                     textTransform: "uppercase",
                  }}>
                  Evidence Card Skeleton
               </div>
               <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {[1, 2, 3].map((i) => (
                     <div
                        key={i}
                        style={{
                           background: "#fff",
                           border: "1.5px solid #e5e7eb",
                           borderLeft: `4px solid #f3f4f6`,
                           borderRadius: 8,
                           padding: "12px 16px",
                           display: "flex",
                           flexDirection: "column",
                           gap: 7,
                        }}>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                           <div
                              style={{
                                 width: 28,
                                 height: 28,
                                 borderRadius: "50%",
                                 background: "#f3f4f6",
                              }}
                           />
                           <SkeletonLine
                              w="35%"
                              h={9}
                           />
                           <SkeletonLine
                              w="15%"
                              h={16}
                           />
                        </div>
                        <SkeletonLine w="95%" />
                        <SkeletonLine w="80%" />
                     </div>
                  ))}
               </div>
            </div>
         </div>
         <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 24 }}>
            <Ann
               title="Empty State Pattern"
               BoxIcon={Puzzle}
               color={T.indigo}
               items={[
                  "Icon → Title → Description → Single CTA (never two buttons)",
                  "Icon background uses diluted semantic colour matching the context",
                  "CTA copies the action language: 'Flag a Claim' not 'Get Started'",
                  "Place empty states in the same position the content would appear — no layout shift",
               ]}
            />
            <Ann
               title="Skeleton Loading"
               BoxIcon={RefreshCw}
               color={T.amber}
               items={[
                  "Use CSS shimmer animation: background-position shift via keyframes",
                  "Avatar: circle placeholder same size as real avatar — prevents layout jump",
                  "Image block: fixed height (same as real card) — no collapsing",
                  "Show 3 skeleton cards immediately on mount, replace with real data as it loads",
               ]}
            />
         </div>
      </div>
   );
};

// ─── View: Onboarding Flow ─────────────────────────────────────────────────────
const OnboardingFlow = () => {
   const [step, setStep] = useState(0);
   const steps = [
      { id: 0, label: "Welcome", Icon: Sparkles },
      { id: 1, label: "Install", Icon: Download },
      { id: 2, label: "First Scan", Icon: ScanLine },
      { id: 3, label: "Community", Icon: Users },
   ];
   const content = [
      {
         heading: "Welcome to TruthLens",
         sub: "You're joining a community of 10,000+ fact-checkers. Here's how to get the most out of your account.",
         body: (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
               {[
                  {
                     Icon: ScanLine,
                     label: "Snip & Scan",
                     desc: "Capture suspicious claims directly from any webpage",
                  },
                  {
                     Icon: Users,
                     label: "Community Votes",
                     desc: "Earn Trust Score by submitting verified evidence",
                  },
                  {
                     Icon: Shield,
                     label: "AI + Human",
                     desc: "AI gives a first verdict — the community settles it",
                  },
               ].map(({ Icon: SI, label, desc }) => (
                  <div
                     key={label}
                     style={{
                        display: "flex",
                        gap: 12,
                        alignItems: "center",
                        background: "rgba(255,255,255,0.08)",
                        borderRadius: 10,
                        padding: "12px 16px",
                     }}>
                     <div
                        style={{
                           width: 36,
                           height: 36,
                           borderRadius: 9,
                           background: "rgba(79,70,229,0.4)",
                           display: "flex",
                           alignItems: "center",
                           justifyContent: "center",
                           flexShrink: 0,
                        }}>
                        <SI
                           size={16}
                           color="#fff"
                           strokeWidth={2}
                        />
                     </div>
                     <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>{label}</div>
                        <div style={{ fontSize: 11, color: "rgba(255,255,255,0.6)" }}>{desc}</div>
                     </div>
                  </div>
               ))}
            </div>
         ),
         cta: "Let's Get Started",
      },
      {
         heading: "Install the Chrome Extension",
         sub: "The extension lets you snip claims directly from any webpage — no copy-pasting needed.",
         body: (
            <div
               style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
               <div
                  style={{
                     width: 80,
                     height: 80,
                     borderRadius: 20,
                     background: "rgba(255,255,255,0.12)",
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "center",
                  }}>
                  <Download
                     size={36}
                     color="#fff"
                     strokeWidth={1.5}
                  />
               </div>
               <button
                  style={{
                     fontSize: 14,
                     fontWeight: 800,
                     color: T.indigo,
                     background: "#fff",
                     border: "none",
                     borderRadius: 10,
                     padding: "12px 28px",
                     cursor: "pointer",
                     display: "flex",
                     alignItems: "center",
                     gap: 8,
                  }}>
                  <Download
                     size={16}
                     color={T.indigo}
                  />{" "}
                  Add to Chrome — Free
               </button>
               <div style={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}>
                  Supports Chrome 88+. No account data shared with browser.
               </div>
            </div>
         ),
         cta: "I've Installed It",
      },
      {
         heading: "Make Your First Scan",
         sub: "Open any news article or social media post and click the TruthLens extension icon to snip a claim.",
         body: (
            <div
               style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
               {[
                  { n: 1, t: "Click the TruthLens icon in your toolbar" },
                  { n: 2, t: "Select 'Snip' and drag over the claim" },
                  { n: 3, t: "Wait for AI analysis — usually under 3 seconds" },
                  { n: 4, t: "See your verdict and share to community if uncertain" },
               ].map(({ n, t }) => (
                  <div
                     key={n}
                     style={{
                        display: "flex",
                        gap: 12,
                        alignItems: "center",
                        width: "100%",
                        maxWidth: 360,
                        background: "rgba(255,255,255,0.08)",
                        borderRadius: 9,
                        padding: "10px 14px",
                     }}>
                     <div
                        style={{
                           width: 24,
                           height: 24,
                           borderRadius: "50%",
                           background: T.indigo,
                           display: "flex",
                           alignItems: "center",
                           justifyContent: "center",
                           flexShrink: 0,
                        }}>
                        <span style={{ fontSize: 11, fontWeight: 900, color: "#fff" }}>{n}</span>
                     </div>
                     <span
                        style={{ fontSize: 12, color: "rgba(255,255,255,0.85)", fontWeight: 500 }}>
                        {t}
                     </span>
                  </div>
               ))}
            </div>
         ),
         cta: "Got It",
      },
      {
         heading: "You're Ready!",
         sub: "Start exploring the community feed, vote on evidence, and build your Trust Score.",
         body: (
            <div
               style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
               <div
                  style={{
                     width: 72,
                     height: 72,
                     borderRadius: "50%",
                     background: "rgba(14,159,110,0.2)",
                     border: `2px solid ${T.green}`,
                     display: "flex",
                     alignItems: "center",
                     justifyContent: "center",
                  }}>
                  <CheckCircle2
                     size={32}
                     color={T.green}
                     strokeWidth={2}
                  />
               </div>
               <div style={{ fontSize: 15, fontWeight: 700, color: "#fff" }}>
                  Account setup complete
               </div>
               <div style={{ display: "flex", gap: 12 }}>
                  <div
                     style={{
                        background: "rgba(255,255,255,0.1)",
                        borderRadius: 10,
                        padding: "10px 14px",
                        textAlign: "center",
                     }}>
                     <div style={{ fontSize: 16, fontWeight: 900, color: "#fff" }}>0</div>
                     <div
                        style={{
                           fontSize: 9,
                           color: "rgba(255,255,255,0.5)",
                           fontWeight: 700,
                           textTransform: "uppercase",
                           letterSpacing: "0.06em",
                        }}>
                        Scans
                     </div>
                  </div>
                  <div
                     style={{
                        background: "rgba(255,255,255,0.1)",
                        borderRadius: 10,
                        padding: "10px 14px",
                        textAlign: "center",
                     }}>
                     <div style={{ fontSize: 16, fontWeight: 900, color: "#fff" }}>50</div>
                     <div
                        style={{
                           fontSize: 9,
                           color: "rgba(255,255,255,0.5)",
                           fontWeight: 700,
                           textTransform: "uppercase",
                           letterSpacing: "0.06em",
                        }}>
                        Starting Score
                     </div>
                  </div>
               </div>
            </div>
         ),
         cta: "Explore the Feed",
      },
   ];
   const cur = content[step];
   const prog = ((step + 1) / steps.length) * 100;
   return (
      <div style={{ padding: "0 0 48px" }}>
         {/* Browser-style wrapper using same gradient as auth */}
         <div
            style={{
               overflow: "hidden",
               borderTop: "1px solid #d1d5db",
               borderBottom: "1px solid #d1d5db",
               boxShadow: "0 8px 40px rgba(0,0,0,0.18)",
            }}>
            <div
               style={{
                  background: "#e8e8e8",
                  padding: "10px 16px",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  borderBottom: "1px solid #d0d0d0",
               }}>
               <div style={{ display: "flex", gap: 6 }}>
                  {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
                     <div
                        key={c}
                        style={{ width: 12, height: 12, borderRadius: "50%", background: c }}
                     />
                  ))}
               </div>
               <div
                  style={{
                     flex: 1,
                     background: "#fff",
                     borderRadius: 6,
                     padding: "5px 14px",
                     fontSize: 12,
                     color: "#555",
                     border: "1px solid #c8c8c8",
                     display: "flex",
                     alignItems: "center",
                     gap: 6,
                  }}>
                  <span style={{ fontSize: 11, color: "#999" }}>https://</span>
                  <span style={{ fontWeight: 600, color: "#333" }}>truthlens.app</span>
                  <span style={{ color: "#999" }}>/onboarding</span>
               </div>
            </div>
            <div
               style={{
                  background: `linear-gradient(160deg,${T.dark} 0%,#2d2a6e 60%,${T.indigo} 100%)`,
                  minHeight: "calc(100vh - 160px)",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "40px 24px",
                  position: "relative",
               }}>
               {/* SVG dot grid */}
               <svg
                  style={{
                     position: "absolute",
                     inset: 0,
                     opacity: 0.06,
                     width: "100%",
                     height: "100%",
                  }}>
                  <defs>
                     <pattern
                        id="odots"
                        width="28"
                        height="28"
                        patternUnits="userSpaceOnUse">
                        <circle
                           cx="2"
                           cy="2"
                           r="1.8"
                           fill="white"
                        />
                     </pattern>
                  </defs>
                  <rect
                     width="100%"
                     height="100%"
                     fill="url(#odots)"
                  />
               </svg>
               {/* Logo */}
               <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 32 }}>
                  <Logo size={16} />
                  <span style={{ color: "#fff", fontWeight: 900, fontSize: 16 }}>TruthLens</span>
               </div>
               {/* Step indicators */}
               <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
                  {steps.map((s, i) => (
                     <div
                        key={s.id}
                        onClick={() => setStep(i)}
                        style={{
                           display: "flex",
                           alignItems: "center",
                           gap: 6,
                           cursor: "pointer",
                           opacity: i === step ? 1 : 0.5,
                        }}>
                        <div
                           style={{
                              width: 28,
                              height: 28,
                              borderRadius: "50%",
                              background:
                                 i <= step ? "rgba(79,70,229,0.8)" : "rgba(255,255,255,0.1)",
                              border: `2px solid ${i <= step ? T.indigo : "rgba(255,255,255,0.2)"}`,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                           }}>
                           {i < step ? (
                              <Check
                                 size={12}
                                 color="#fff"
                                 strokeWidth={3}
                              />
                           ) : (
                              <span style={{ fontSize: 10, fontWeight: 800, color: "#fff" }}>
                                 {i + 1}
                              </span>
                           )}
                        </div>
                        {i < steps.length - 1 && (
                           <div
                              style={{
                                 width: 24,
                                 height: 1,
                                 background:
                                    i < step ? "rgba(79,70,229,0.6)" : "rgba(255,255,255,0.15)",
                              }}
                           />
                        )}
                     </div>
                  ))}
               </div>
               {/* Progress bar */}
               <div
                  style={{
                     width: "100%",
                     maxWidth: 460,
                     height: 3,
                     background: "rgba(255,255,255,0.1)",
                     borderRadius: 99,
                     marginBottom: 36,
                  }}>
                  <div
                     style={{
                        height: "100%",
                        width: `${prog}%`,
                        background: T.indigo,
                        borderRadius: 99,
                        transition: "width 0.3s",
                     }}
                  />
               </div>
               {/* Content card */}
               <div
                  style={{
                     width: "100%",
                     maxWidth: 460,
                     background: "rgba(255,255,255,0.07)",
                     backdropFilter: "blur(12px)",
                     borderRadius: 18,
                     border: "1px solid rgba(255,255,255,0.12)",
                     padding: "28px 28px 24px",
                     marginBottom: 24,
                  }}>
                  <div
                     style={{
                        fontSize: 22,
                        fontWeight: 900,
                        color: "#fff",
                        letterSpacing: "-0.02em",
                        marginBottom: 6,
                     }}>
                     {cur.heading}
                  </div>
                  <div
                     style={{
                        fontSize: 12,
                        color: "rgba(255,255,255,0.65)",
                        lineHeight: 1.6,
                        marginBottom: 20,
                     }}>
                     {cur.sub}
                  </div>
                  {cur.body}
               </div>
               {/* Nav */}
               <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                  {step > 0 && (
                     <button
                        onClick={() => setStep((s) => s - 1)}
                        style={{
                           fontSize: 12,
                           fontWeight: 700,
                           color: "rgba(255,255,255,0.6)",
                           background: "rgba(255,255,255,0.08)",
                           border: "1.5px solid rgba(255,255,255,0.15)",
                           borderRadius: 9,
                           padding: "10px 20px",
                           cursor: "pointer",
                        }}>
                        ← Back
                     </button>
                  )}
                  <button
                     onClick={() => setStep((s) => Math.min(s + 1, steps.length - 1))}
                     style={{
                        fontSize: 13,
                        fontWeight: 800,
                        color: "#fff",
                        background: step === steps.length - 1 ? T.green : T.indigo,
                        border: "none",
                        borderRadius: 9,
                        padding: "10px 28px",
                        cursor: "pointer",
                        letterSpacing: "0.02em",
                     }}>
                     {cur.cta} →
                  </button>
               </div>
               <div
                  style={{
                     marginTop: 16,
                     fontSize: 10,
                     color: "rgba(255,255,255,0.3)",
                     cursor: "pointer",
                  }}>
                  Skip setup →
               </div>
            </div>
         </div>
         {/* Annotations */}
         <div
            style={{
               display: "grid",
               gridTemplateColumns: "1fr 1fr",
               gap: 16,
               marginTop: 28,
               padding: "0 32px",
            }}>
            <Ann
               title="Flow Structure"
               BoxIcon={Ruler}
               color={T.indigo}
               items={[
                  "4 steps: Welcome → Install Extension → First Scan → Complete",
                  "Progress bar + numbered step indicators — user always knows where they are",
                  "Step indicators are clickable (dev mode) — use router or state machine in production",
                  "Skip link at bottom — never force onboarding, let curious users explore",
               ]}
            />
            <Ann
               title="UX / Conversion Notes"
               BoxIcon={Puzzle}
               color={T.violet}
               items={[
                  "Step 2 'Install' CTA opens Chrome Web Store in new tab — don't navigate away",
                  "Step 3 transitions after extension sends a 'first_scan_complete' event via postMessage",
                  "Step 4 shows the user's starting Trust Score (50) — immediate sense of progress",
                  "After onboarding, set onboarded=true in user profile — never show again",
               ]}
            />
         </div>
      </div>
   );
};

// ─── View: Moderation / Admin Panel ───────────────────────────────────────────
const ModerationPanel = () => {
   const [activeTab, setActiveTab] = useState("queue");
   const queue = [
      {
         id: "F-001",
         type: "Evidence",
         claim: "Valencia flooding photo",
         reporter: "@newscheck",
         reason: "Misleading source link — URL redirects to known disinfo site",
         status: "pending",
         severity: "high",
      },
      {
         id: "F-002",
         type: "Comment",
         claim: "Mask effectiveness thread",
         reporter: "@verifyme",
         reason: "Personal attack / harassment toward evidence submitter",
         status: "pending",
         severity: "medium",
      },
      {
         id: "F-003",
         type: "Thread",
         claim: "Senator healthcare vote",
         reporter: "@factchecker_ph",
         reason: "Suspected coordinated voting — 40 upvotes in 2 minutes",
         status: "reviewing",
         severity: "high",
      },
      {
         id: "F-004",
         type: "Evidence",
         claim: "5G cancer claim",
         reporter: "@scicheck",
         reason: "Evidence source is behind paywall — community cannot verify",
         status: "pending",
         severity: "low",
      },
   ];
   const severityColor = { high: T.red, medium: T.amber, low: T.gray };
   const statusColor = { pending: T.amber, reviewing: T.indigo, resolved: T.green };
   return (
      <div style={{ background: "#f1f5f9", minHeight: "100%" }}>
         {/* Mod nav — extends AppNav with mod indicator */}
         <div
            style={{
               background: T.dark,
               padding: "0 32px",
               display: "flex",
               alignItems: "center",
               gap: 0,
               boxShadow: "0 2px 12px rgba(0,0,0,0.25)",
               position: "sticky",
               top: 0,
               zIndex: 50,
            }}>
            <div
               style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "12px 0",
                  marginRight: 28,
                  borderRight: "1px solid rgba(255,255,255,0.08)",
                  paddingRight: 28,
               }}>
               <Logo size={14} />
               <span style={{ color: "#fff", fontWeight: 900, fontSize: 15 }}>TruthLens</span>
               <span
                  style={{
                     fontSize: 9,
                     fontWeight: 800,
                     color: T.red,
                     background: "rgba(224,36,36,0.2)",
                     border: `1px solid rgba(224,36,36,0.4)`,
                     borderRadius: 5,
                     padding: "2px 7px",
                     letterSpacing: "0.06em",
                  }}>
                  MOD
               </span>
            </div>
            <div style={{ display: "flex", gap: 2, flex: 1 }}>
               {["Flag Queue", "Override Verdicts", "User Management", "Audit Log"].map(
                  (label, i) => (
                     <div
                        key={label}
                        style={{
                           padding: "12px 14px",
                           fontSize: 12,
                           fontWeight: 600,
                           display: "flex",
                           alignItems: "center",
                           gap: 7,
                           color: i === 0 ? "#fff" : "rgba(255,255,255,0.45)",
                           borderBottom: i === 0 ? `2px solid ${T.red}` : "2px solid transparent",
                           cursor: "pointer",
                        }}>
                        {label}
                        {i === 0 && (
                           <span
                              style={{
                                 fontSize: 9,
                                 fontWeight: 800,
                                 color: "#fff",
                                 background: T.red,
                                 borderRadius: "50%",
                                 width: 16,
                                 height: 16,
                                 display: "flex",
                                 alignItems: "center",
                                 justifyContent: "center",
                              }}>
                              4
                           </span>
                        )}
                     </div>
                  ),
               )}
            </div>
            <div
               style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 7,
                  background: "rgba(255,255,255,0.07)",
                  borderRadius: 8,
                  padding: "6px 12px",
               }}>
               <Avatar
                  Icon={Shield}
                  bg="rgba(224,36,36,0.2)"
                  color={T.red}
                  size={26}
               />
               <span style={{ fontSize: 12, fontWeight: 600, color: "rgba(255,255,255,0.8)" }}>
                  @admin
               </span>
            </div>
         </div>
         <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 24px 64px" }}>
            {/* Stats header */}
            <div
               style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(4,1fr)",
                  gap: 14,
                  marginBottom: 24,
               }}>
               {[
                  { label: "Flags Pending", val: "4", color: T.amber, Icon: Flag },
                  { label: "Resolved Today", val: "12", color: T.green, Icon: CheckCircle2 },
                  { label: "Avg. Resolution", val: "1.4h", color: T.indigo, Icon: Clock },
                  { label: "Active Reviewers", val: "3", color: T.violet, Icon: Users },
               ].map(({ label, val, color, Icon: SI }) => (
                  <div
                     key={label}
                     style={{
                        background: "#fff",
                        border: "1.5px solid #e5e7eb",
                        borderRadius: 10,
                        padding: "16px 18px",
                        borderTop: `3px solid ${color}`,
                     }}>
                     <div
                        style={{
                           display: "flex",
                           justifyContent: "space-between",
                           alignItems: "flex-start",
                        }}>
                        <div>
                           <div style={{ fontSize: 24, fontWeight: 900, color: "#111827" }}>
                              {val}
                           </div>
                           <div
                              style={{
                                 fontSize: 10,
                                 color: T.gray,
                                 fontWeight: 700,
                                 textTransform: "uppercase",
                                 letterSpacing: "0.06em",
                              }}>
                              {label}
                           </div>
                        </div>
                        <SI
                           size={18}
                           color={color}
                           strokeWidth={1.8}
                        />
                     </div>
                  </div>
               ))}
            </div>
            {/* Flag queue */}
            <SLabel>Flag Queue</SLabel>
            <div
               style={{
                  background: "#fff",
                  border: "1.5px solid #e5e7eb",
                  borderRadius: 12,
                  overflow: "hidden",
               }}>
               <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                     <tr style={{ background: "#f9fafb", borderBottom: "1.5px solid #e5e7eb" }}>
                        {[
                           "ID",
                           "Type",
                           "Thread / Claim",
                           "Reporter",
                           "Reason",
                           "Severity",
                           "Status",
                           "Actions",
                        ].map((h) => (
                           <th
                              key={h}
                              style={{
                                 textAlign: "left",
                                 padding: "10px 14px",
                                 fontSize: 10,
                                 fontWeight: 800,
                                 color: T.gray,
                                 letterSpacing: "0.06em",
                                 whiteSpace: "nowrap",
                              }}>
                              {h}
                           </th>
                        ))}
                     </tr>
                  </thead>
                  <tbody>
                     {queue.map((item, i) => (
                        <tr
                           key={item.id}
                           style={{
                              borderBottom: i < queue.length - 1 ? "1px solid #f3f4f6" : "none",
                           }}>
                           <td
                              style={{
                                 padding: "12px 14px",
                                 fontSize: 11,
                                 color: T.gray,
                                 fontFamily: "monospace",
                              }}>
                              {item.id}
                           </td>
                           <td style={{ padding: "12px 14px" }}>
                              <span
                                 style={{
                                    fontSize: 10,
                                    fontWeight: 700,
                                    color: T.indigo,
                                    background: "#eff6ff",
                                    borderRadius: 4,
                                    padding: "2px 7px",
                                 }}>
                                 {item.type}
                              </span>
                           </td>
                           <td
                              style={{
                                 padding: "12px 14px",
                                 fontSize: 12,
                                 color: "#374151",
                                 maxWidth: 160,
                              }}>
                              {item.claim}
                           </td>
                           <td
                              style={{
                                 padding: "12px 14px",
                                 fontSize: 11,
                                 color: T.indigo,
                                 fontWeight: 600,
                              }}>
                              {item.reporter}
                           </td>
                           <td
                              style={{
                                 padding: "12px 14px",
                                 fontSize: 11,
                                 color: "#374151",
                                 maxWidth: 200,
                              }}>
                              {item.reason}
                           </td>
                           <td style={{ padding: "12px 14px" }}>
                              <span
                                 style={{
                                    fontSize: 10,
                                    fontWeight: 800,
                                    color: severityColor[item.severity],
                                    background:
                                       item.severity === "high"
                                          ? "#fee2e2"
                                          : item.severity === "medium"
                                            ? "#fef3c7"
                                            : "#f3f4f6",
                                    borderRadius: 4,
                                    padding: "2px 8px",
                                    textTransform: "uppercase",
                                    letterSpacing: "0.05em",
                                 }}>
                                 {item.severity}
                              </span>
                           </td>
                           <td style={{ padding: "12px 14px" }}>
                              <span
                                 style={{
                                    fontSize: 10,
                                    fontWeight: 700,
                                    color: statusColor[item.status],
                                    background: "transparent",
                                    borderRadius: 4,
                                    padding: "2px 0",
                                 }}>
                                 {item.status}
                              </span>
                           </td>
                           <td style={{ padding: "12px 14px" }}>
                              <div style={{ display: "flex", gap: 5 }}>
                                 <button
                                    style={{
                                       fontSize: 10,
                                       fontWeight: 700,
                                       color: "#fff",
                                       background: T.green,
                                       border: "none",
                                       borderRadius: 4,
                                       padding: "4px 8px",
                                       cursor: "pointer",
                                    }}>
                                    Approve
                                 </button>
                                 <button
                                    style={{
                                       fontSize: 10,
                                       fontWeight: 700,
                                       color: "#fff",
                                       background: T.red,
                                       border: "none",
                                       borderRadius: 4,
                                       padding: "4px 8px",
                                       cursor: "pointer",
                                    }}>
                                    Remove
                                 </button>
                                 <button
                                    style={{
                                       fontSize: 10,
                                       fontWeight: 700,
                                       color: T.gray,
                                       background: "#f3f4f6",
                                       border: "none",
                                       borderRadius: 4,
                                       padding: "4px 8px",
                                       cursor: "pointer",
                                    }}>
                                    Warn
                                 </button>
                              </div>
                           </td>
                        </tr>
                     ))}
                  </tbody>
               </table>
            </div>
            {/* Override Verdicts section */}
            <SLabel style={{ marginTop: 24 }}>Verdict Override Panel</SLabel>
            <div
               style={{
                  background: "#fff",
                  border: "1.5px solid #e5e7eb",
                  borderRadius: 12,
                  padding: "18px 20px",
                  marginTop: 12,
               }}>
               <div style={{ fontSize: 12, color: "#374151", marginBottom: 14, lineHeight: 1.6 }}>
                  Moderators can override AI verdicts when community consensus is clear but the AI
                  classification is wrong. All overrides are logged in the Audit Log.
               </div>
               <div style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
                  <div style={{ flex: 1 }}>
                     <div
                        style={{
                           fontSize: 10,
                           fontWeight: 700,
                           color: T.gray,
                           letterSpacing: "0.06em",
                           textTransform: "uppercase",
                           marginBottom: 4,
                        }}>
                        Thread / Claim ID
                     </div>
                     <div
                        style={{
                           border: "1.5px solid #e5e7eb",
                           borderRadius: 7,
                           padding: "8px 12px",
                           fontSize: 12,
                           color: "#9ca3af",
                           background: "#fafafa",
                        }}>
                        Enter Thread ID or claim URL…
                     </div>
                  </div>
                  <div>
                     <div
                        style={{
                           fontSize: 10,
                           fontWeight: 700,
                           color: T.gray,
                           letterSpacing: "0.06em",
                           textTransform: "uppercase",
                           marginBottom: 4,
                        }}>
                        Override Verdict
                     </div>
                     <div style={{ display: "flex", gap: 6 }}>
                        {["verified", "fake", "misleading", "unverified"].map((v) => (
                           <span
                              key={v}
                              style={{ cursor: "pointer" }}>
                              <VerdictBadge verdict={v} />
                           </span>
                        ))}
                     </div>
                  </div>
                  <button
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: "#fff",
                        background: T.indigo,
                        border: "none",
                        borderRadius: 7,
                        padding: "9px 18px",
                        cursor: "pointer",
                     }}>
                     Apply Override
                  </button>
               </div>
            </div>
         </div>
      </div>
   );
};

// ─── View: Mobile Feed ────────────────────────────────────────────────────────
const MobileFeed = () => {
   const posts = [
      {
         verdict: "fake",
         author: "@photocheck",
         time: "2h",
         caption:
            '"Shocking aerial photo shows the aftermath of the 2024 flooding in Valencia, Spain."',
         confidence: 94,
         reactions: 142,
         comments: 89,
         evidence: 15,
      },
      {
         verdict: "misleading",
         author: "@skepticwatch",
         time: "5h",
         caption: '"New study proves masks are completely ineffective against airborne COVID."',
         confidence: 62,
         reactions: 78,
         comments: 34,
         evidence: 7,
      },
      {
         verdict: "satire",
         author: "@theonion_watch",
         time: "3h",
         caption: '"Scientists Discover New Planet Composed Entirely Of Student Loan Debt"',
         confidence: 99,
         reactions: 312,
         comments: 57,
         evidence: 4,
      },
   ];
   const borderColor = (v) =>
      ({
         verified: T.green,
         fake: T.red,
         misleading: T.amber,
         unverified: T.gray,
         satire: T.violet,
      })[v] || T.gray;
   const avatarEl = (av) => {
      const m = {
         detective: { Icon: Eye, bg: "#fce7f3", color: "#be185d" },
         news: { Icon: Newspaper, bg: "#fef3c7", color: "#92400e" },
         satire: { Icon: Wand2, bg: "#ede9fe", color: T.violet },
      };
      const a = m[av] || { Icon: User, bg: "#f3f4f6", color: T.gray };
      return (
         <Avatar
            Icon={a.Icon}
            bg={a.bg}
            color={a.color}
            size={32}
         />
      );
   };
   return (
      <div style={{ display: "flex", gap: 32, alignItems: "flex-start", flexWrap: "wrap" }}>
         {/* Device frame */}
         <div>
            <SLabel>Mobile Feed — 390px viewport (iPhone 15 Pro)</SLabel>
            <div
               style={{
                  width: 390,
                  borderRadius: 40,
                  background: T.dark,
                  padding: "12px 8px 8px",
                  boxShadow: "0 24px 64px rgba(0,0,0,0.4)",
                  border: "8px solid #1a1a2e",
               }}>
               {/* Status bar */}
               <div
                  style={{
                     display: "flex",
                     justifyContent: "space-between",
                     alignItems: "center",
                     padding: "0 20px 10px",
                  }}>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#fff" }}>9:41</span>
                  <div
                     style={{
                        width: 120,
                        height: 30,
                        background: "#000",
                        borderRadius: 99,
                        margin: "-8px auto 0",
                     }}
                  />
                  <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
                     <Activity
                        size={12}
                        color="#fff"
                     />
                     <Zap
                        size={12}
                        color="#fff"
                     />
                  </div>
               </div>
               {/* Screen */}
               <div
                  style={{
                     background: "#f1f5f9",
                     borderRadius: 32,
                     overflow: "hidden",
                     height: 720,
                     position: "relative",
                  }}>
                  {/* Mobile top bar — compact */}
                  <div
                     style={{
                        background: T.dark,
                        padding: "10px 16px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                     }}>
                     <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                        <Logo size={12} />
                        <span style={{ color: "#fff", fontWeight: 800, fontSize: 13 }}>
                           TruthLens
                        </span>
                     </div>
                     <div style={{ display: "flex", gap: 10 }}>
                        <Search
                           size={16}
                           color="rgba(255,255,255,0.7)"
                        />
                        <Bell
                           size={16}
                           color="rgba(255,255,255,0.7)"
                        />
                     </div>
                  </div>
                  {/* Feed */}
                  <div
                     style={{
                        overflowY: "auto",
                        height: "calc(720px - 50px - 56px)",
                        padding: "10px 8px 0",
                     }}>
                     {posts.map((post, i) => (
                        <div
                           key={i}
                           style={{
                              background: "#fff",
                              borderRadius: 12,
                              border: "1.5px solid #e5e7eb",
                              marginBottom: 10,
                              overflow: "hidden",
                           }}>
                           <div
                              style={{
                                 padding: "10px 12px 8px",
                                 display: "flex",
                                 alignItems: "center",
                                 justifyContent: "space-between",
                              }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                 {avatarEl(["detective", "news", "satire"][i])}
                                 <div>
                                    <div
                                       style={{ fontSize: 12, fontWeight: 700, color: "#111827" }}>
                                       {post.author}
                                    </div>
                                    <div style={{ fontSize: 10, color: T.gray }}>
                                       {post.time} · via TruthLens
                                    </div>
                                 </div>
                              </div>
                              <VerdictBadge verdict={post.verdict} />
                           </div>
                           <div
                              style={{
                                 padding: "0 12px 8px",
                                 fontSize: 12,
                                 color: "#1f2937",
                                 lineHeight: 1.5,
                              }}>
                              {post.caption}
                           </div>
                           <div
                              style={{
                                 position: "relative",
                                 height: 100,
                                 background: "linear-gradient(135deg,#e0e7ff,#f3f4f6)",
                                 display: "flex",
                                 alignItems: "center",
                                 justifyContent: "center",
                              }}>
                              <Image
                                 size={22}
                                 color={T.gray}
                                 strokeWidth={1.5}
                              />
                              <div
                                 style={{
                                    position: "absolute",
                                    bottom: 0,
                                    inset: "auto 0 0",
                                    background: `${borderColor(post.verdict)}18`,
                                    borderTop: `3px solid ${borderColor(post.verdict)}`,
                                    padding: "4px 10px",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 6,
                                 }}>
                                 <span style={{ fontSize: 9, color: "#374151", fontWeight: 600 }}>
                                    AI: <strong>{post.confidence}%</strong>
                                 </span>
                              </div>
                           </div>
                           {/* Compact action row */}
                           <div style={{ padding: "6px 8px", display: "flex" }}>
                              {[
                                 { Icon: ThumbsUp, label: `${post.reactions}` },
                                 { Icon: MessageCircle, label: `${post.comments}` },
                                 { Icon: Paperclip, label: "Evidence", color: T.indigo },
                              ].map(({ Icon: AI, label, color }, j) => (
                                 <button
                                    key={j}
                                    style={{
                                       flex: 1,
                                       padding: "6px 2px",
                                       background: "transparent",
                                       border: "none",
                                       fontSize: 11,
                                       fontWeight: 600,
                                       color: color || "#374151",
                                       cursor: "pointer",
                                       display: "flex",
                                       alignItems: "center",
                                       justifyContent: "center",
                                       gap: 4,
                                    }}>
                                    <AI
                                       size={12}
                                       strokeWidth={2}
                                    />{" "}
                                    {label}
                                 </button>
                              ))}
                           </div>
                        </div>
                     ))}
                  </div>
                  {/* Bottom tab bar */}
                  <div
                     style={{
                        position: "absolute",
                        bottom: 0,
                        left: 0,
                        right: 0,
                        background: "#fff",
                        borderRadius: "0 0 32px 32px",
                        padding: "8px 0 12px",
                        boxShadow: "0 -2px 20px rgba(0,0,0,0.12)",
                        display: "flex",
                        border: "none",
                        borderTop: "1px solid #e5e7eb",
                     }}>
                     {[
                        { Icon: Home, label: "Feed", active: true },
                        { Icon: Search, label: "Search" },
                        { Icon: ScanLine, label: "Scan" },
                        { Icon: Bell, label: "Alerts" },
                        { Icon: UserCircle, label: "Me" },
                     ].map(({ Icon: TI, label, active }) => (
                        <div
                           key={label}
                           style={{
                              flex: 1,
                              display: "flex",
                              flexDirection: "column",
                              alignItems: "center",
                              gap: 2,
                              cursor: "pointer",
                           }}>
                           <TI
                              size={18}
                              color={active ? T.indigo : T.gray}
                              strokeWidth={active ? 2.5 : 1.8}
                           />
                           <span
                              style={{
                                 fontSize: 9,
                                 fontWeight: active ? 700 : 500,
                                 color: active ? T.indigo : T.gray,
                              }}>
                              {label}
                           </span>
                        </div>
                     ))}
                  </div>
               </div>
            </div>
         </div>
         {/* Annotations panel */}
         <div style={{ flex: 1, minWidth: 280 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
               <Ann
                  title="Mobile Layout Changes"
                  BoxIcon={Smartphone}
                  color={T.indigo}
                  items={[
                     "Top nav: compact — logo + name only, Search + Bell icons right-aligned",
                     "Sidebar / top page nav removed — replaced by bottom tab bar (5 items)",
                     "PostCard: tighter padding, image height reduced to 100px, avatar 32px",
                     "Verdict badge moves to top-right of card header (not image overlay)",
                     "Bottom tab bar: Home · Search · Scan (prominent) · Alerts · Me",
                  ]}
               />
               <Ann
                  title="Bottom Tab Bar Design"
                  BoxIcon={Layers}
                  color={T.violet}
                  items={[
                     "'Scan' is the centre tab — bigger or accented to highlight primary action",
                     "Tab bar uses position:fixed bottom-0, safe-area-inset-bottom for notch devices",
                     "Active tab: icon strokeWidth 2.5 + indigo colour + bold label",
                     "Use react-navigation (React Native) or CSS position:fixed (web PWA)",
                  ]}
               />
               <Ann
                  title="Responsive Strategy"
                  BoxIcon={MonitorSmartphone}
                  color={T.green}
                  items={[
                     "Breakpoint: < 768px switches to mobile layout",
                     "Bottom tab replaces AppNav via CSS media query or conditional render",
                     "Feed column: full-width with 8px side padding (no maxWidth constraint)",
                     "Touch targets minimum 44×44px — all buttons meet this threshold",
                  ]}
               />
            </div>
         </div>
      </div>
   );
};

// ─── View: Landing Page (Redesigned) ──────────────────────────────────────────
const LandingPage = () => {
   const stats = [
      { val: "12,040+", label: "Images Verified" },
      { val: "500+", label: "Active Contributors" },
      { val: "98%", label: "Accuracy Rate" },
      { val: "10k+", label: "Community Members" },
   ];
   const steps = [
      {
         n: 1,
         Icon: Scissors,
         label: "Snip",
         desc: "Select any suspicious claim or image directly from your feed using our Chrome extension.",
      },
      {
         n: 2,
         Icon: Zap,
         label: "Analyze",
         desc: "AI cross-references the claim against thousands of verified sources in under 3 seconds.",
      },
      {
         n: 3,
         Icon: Users,
         label: "Resolve",
         desc: "The community votes on uncertain claims. Your Trust Score grows with every accurate contribution.",
      },
   ];
   const recentPosts = [
      {
         verdict: "fake",
         title: "Valencia flooding photo",
         sub: "Aerial photo is from 2021 Hurricane Ida, not 2024 Spain floods.",
         confidence: 94,
      },
      {
         verdict: "misleading",
         title: "Mask effectiveness study",
         sub: "Study cited has not been peer-reviewed and contradicts CDC guidelines.",
         confidence: 62,
      },
      {
         verdict: "verified",
         title: "Unemployment figures",
         sub: "BLS data confirms headline claim is accurate within margin of error.",
         confidence: 97,
      },
   ];
   const bc = (v) => ({ verified: T.green, fake: T.red, misleading: T.amber })[v] || T.gray;
   return (
      <div style={{ background: "#fff", minHeight: "100%" }}>
         {/* Navbar */}
         <div
            style={{
               background: "rgba(255,255,255,0.95)",
               backdropFilter: "blur(8px)",
               borderBottom: "1px solid #e5e7eb",
               padding: "0 48px",
               display: "flex",
               alignItems: "center",
               position: "sticky",
               top: 0,
               zIndex: 50,
               height: 60,
            }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: "auto" }}>
               <Logo size={16} />
               <span
                  style={{
                     fontWeight: 900,
                     fontSize: 16,
                     color: T.dark,
                     letterSpacing: "-0.01em",
                  }}>
                  TruthLens
               </span>
            </div>
            <div style={{ display: "flex", gap: 28, alignItems: "center" }}>
               {["Features", "Community", "About"].map((l) => (
                  <span
                     key={l}
                     style={{ fontSize: 13, fontWeight: 600, color: "#374151", cursor: "pointer" }}>
                     {l}
                  </span>
               ))}
               <div style={{ width: 1, height: 20, background: "#e5e7eb" }} />
               <span style={{ fontSize: 13, fontWeight: 600, color: T.indigo, cursor: "pointer" }}>
                  Login
               </span>
               <button
                  style={{
                     fontSize: 13,
                     fontWeight: 800,
                     color: "#fff",
                     background: T.indigo,
                     border: "none",
                     borderRadius: 8,
                     padding: "8px 18px",
                     cursor: "pointer",
                  }}>
                  Get Started
               </button>
            </div>
         </div>
         {/* Hero */}
         <div
            style={{
               background: `linear-gradient(160deg,${T.dark} 0%,#2d2a6e 55%,#4338ca 100%)`,
               padding: "72px 48px 80px",
               position: "relative",
               overflow: "hidden",
            }}>
            <svg
               style={{
                  position: "absolute",
                  inset: 0,
                  opacity: 0.05,
                  width: "100%",
                  height: "100%",
               }}>
               <defs>
                  <pattern
                     id="ldots"
                     width="28"
                     height="28"
                     patternUnits="userSpaceOnUse">
                     <circle
                        cx="2"
                        cy="2"
                        r="1.8"
                        fill="white"
                     />
                  </pattern>
               </defs>
               <rect
                  width="100%"
                  height="100%"
                  fill="url(#ldots)"
               />
            </svg>
            <div
               style={{
                  maxWidth: 1100,
                  margin: "0 auto",
                  display: "grid",
                  gridTemplateColumns: "1fr 480px",
                  gap: 48,
                  alignItems: "center",
                  position: "relative",
               }}>
               <div>
                  <div
                     style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 8,
                        background: "rgba(79,70,229,0.3)",
                        border: "1px solid rgba(79,70,229,0.5)",
                        borderRadius: 99,
                        padding: "5px 14px",
                        marginBottom: 20,
                     }}>
                     <Shield
                        size={12}
                        color="#a5b4fc"
                     />
                     <span
                        style={{
                           fontSize: 11,
                           fontWeight: 700,
                           color: "#a5b4fc",
                           letterSpacing: "0.05em",
                        }}>
                        AI-POWERED MEDIA LITERACY
                     </span>
                  </div>
                  <div
                     style={{
                        fontSize: 48,
                        fontWeight: 900,
                        color: "#fff",
                        letterSpacing: "-0.03em",
                        lineHeight: 1.1,
                        marginBottom: 16,
                     }}>
                     See the Truth
                     <br />
                     <span style={{ color: "#818cf8" }}>Behind the Feed.</span>
                  </div>
                  <div
                     style={{
                        fontSize: 16,
                        color: "rgba(255,255,255,0.65)",
                        lineHeight: 1.7,
                        marginBottom: 32,
                        maxWidth: 440,
                     }}>
                     AI-powered shield against misinformation. Snip any claim, get an instant
                     verdict, and let 10,000+ fact-checkers settle the debate.
                  </div>
                  {/* Stats row — in hero */}
                  <div style={{ display: "flex", gap: 28, marginBottom: 32 }}>
                     {stats.map(({ val, label }) => (
                        <div key={label}>
                           <div style={{ fontSize: 20, fontWeight: 900, color: "#fff" }}>{val}</div>
                           <div
                              style={{
                                 fontSize: 10,
                                 color: "rgba(255,255,255,0.5)",
                                 fontWeight: 600,
                                 textTransform: "uppercase",
                                 letterSpacing: "0.06em",
                              }}>
                              {label}
                           </div>
                        </div>
                     ))}
                  </div>
                  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                     <button
                        style={{
                           fontSize: 14,
                           fontWeight: 800,
                           color: "#fff",
                           background: T.indigo,
                           border: "none",
                           borderRadius: 10,
                           padding: "14px 28px",
                           cursor: "pointer",
                           display: "flex",
                           alignItems: "center",
                           gap: 8,
                           letterSpacing: "0.02em",
                        }}>
                        <Download
                           size={16}
                           color="#fff"
                        />{" "}
                        DOWNLOAD FOR CHROME
                     </button>
                     <button
                        style={{
                           fontSize: 13,
                           fontWeight: 700,
                           color: "rgba(255,255,255,0.8)",
                           background: "rgba(255,255,255,0.08)",
                           border: "1.5px solid rgba(255,255,255,0.2)",
                           borderRadius: 10,
                           padding: "14px 22px",
                           cursor: "pointer",
                           display: "flex",
                           alignItems: "center",
                           gap: 6,
                        }}>
                        <Play
                           size={13}
                           color="rgba(255,255,255,0.8)"
                        />{" "}
                        Watch Demo
                     </button>
                  </div>
               </div>
               {/* Hero mockup — extension result card floating over feed */}
               <div style={{ position: "relative" }}>
                  {/* Fake feed bg */}
                  <div
                     style={{
                        background: "rgba(255,255,255,0.06)",
                        borderRadius: 14,
                        border: "1px solid rgba(255,255,255,0.1)",
                        padding: 16,
                     }}>
                     {[1, 2].map((i) => (
                        <div
                           key={i}
                           style={{
                              background: "rgba(255,255,255,0.05)",
                              borderRadius: 8,
                              padding: 12,
                              marginBottom: i < 2 ? 10 : 0,
                           }}>
                           <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                              <div
                                 style={{
                                    width: 28,
                                    height: 28,
                                    borderRadius: "50%",
                                    background: "rgba(255,255,255,0.1)",
                                 }}
                              />
                              <div style={{ flex: 1 }}>
                                 <div
                                    style={{
                                       height: 9,
                                       background: "rgba(255,255,255,0.15)",
                                       borderRadius: 3,
                                       width: "40%",
                                       marginBottom: 5,
                                    }}
                                 />
                                 <div
                                    style={{
                                       height: 7,
                                       background: "rgba(255,255,255,0.08)",
                                       borderRadius: 3,
                                       width: "25%",
                                    }}
                                 />
                              </div>
                           </div>
                           <div
                              style={{
                                 height: 60,
                                 background: "rgba(255,255,255,0.07)",
                                 borderRadius: 6,
                              }}
                           />
                        </div>
                     ))}
                  </div>
                  {/* Floating result card */}
                  <div
                     style={{
                        position: "absolute",
                        top: 16,
                        right: -20,
                        background: "#fff",
                        borderRadius: 12,
                        border: "1.5px solid #e5e7eb",
                        boxShadow: "0 16px 48px rgba(0,0,0,0.3)",
                        padding: "14px 16px",
                        width: 220,
                        borderLeft: `4px solid ${T.red}`,
                     }}>
                     <div
                        style={{
                           display: "flex",
                           justifyContent: "space-between",
                           alignItems: "center",
                           marginBottom: 8,
                        }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                           <Logo size={10} />
                           <span style={{ fontSize: 10, fontWeight: 800, color: T.dark }}>
                              TruthLens
                           </span>
                        </div>
                        <VerdictBadge verdict="fake" />
                     </div>
                     <div
                        style={{
                           fontSize: 10,
                           color: "#374151",
                           lineHeight: 1.5,
                           marginBottom: 8,
                        }}>
                        AI detected this photo is from a 2021 flood event, not 2024.
                     </div>
                     <div
                        style={{
                           height: 4,
                           background: "#fee2e2",
                           borderRadius: 99,
                           marginBottom: 6,
                        }}>
                        <div
                           style={{
                              height: "100%",
                              width: "94%",
                              background: T.red,
                              borderRadius: 99,
                           }}
                        />
                     </div>
                     <div style={{ fontSize: 9, color: T.gray, fontWeight: 600 }}>
                        94% confidence · 15 community sources
                     </div>
                  </div>
               </div>
            </div>
         </div>
         {/* How It Works */}
         <div style={{ padding: "72px 48px", background: "#f9fafb" }}>
            <div style={{ maxWidth: 1100, margin: "0 auto" }}>
               <div style={{ textAlign: "center", marginBottom: 48 }}>
                  <div
                     style={{
                        fontSize: 11,
                        fontWeight: 800,
                        color: T.indigo,
                        letterSpacing: "0.12em",
                        textTransform: "uppercase",
                        marginBottom: 8,
                     }}>
                     HOW IT WORKS
                  </div>
                  <div
                     style={{
                        fontSize: 32,
                        fontWeight: 900,
                        color: T.dark,
                        letterSpacing: "-0.02em",
                     }}>
                     Three steps to the truth
                  </div>
               </div>
               <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 32 }}>
                  {steps.map(({ n, Icon: SI, label, desc }) => (
                     <div
                        key={n}
                        style={{ textAlign: "center" }}>
                        <div
                           style={{
                              width: 64,
                              height: 64,
                              borderRadius: 16,
                              background: `linear-gradient(135deg,${T.indigo},#6366f1)`,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              margin: "0 auto 16px",
                           }}>
                           <SI
                              size={28}
                              color="#fff"
                              strokeWidth={1.8}
                           />
                        </div>
                        <div
                           style={{
                              fontSize: 11,
                              fontWeight: 800,
                              color: T.indigo,
                              letterSpacing: "0.1em",
                              marginBottom: 6,
                           }}>
                           0{n} — {label.toUpperCase()}
                        </div>
                        <div
                           style={{
                              fontSize: 20,
                              fontWeight: 900,
                              color: T.dark,
                              marginBottom: 8,
                           }}>
                           {label}
                        </div>
                        <div style={{ fontSize: 13, color: T.gray, lineHeight: 1.7 }}>{desc}</div>
                     </div>
                  ))}
               </div>
            </div>
         </div>
         {/* Recent Investigations */}
         <div style={{ padding: "72px 48px" }}>
            <div style={{ maxWidth: 1100, margin: "0 auto" }}>
               <div
                  style={{
                     display: "flex",
                     justifyContent: "space-between",
                     alignItems: "flex-end",
                     marginBottom: 32,
                  }}>
                  <div>
                     <div
                        style={{
                           fontSize: 11,
                           fontWeight: 800,
                           color: T.indigo,
                           letterSpacing: "0.12em",
                           textTransform: "uppercase",
                           marginBottom: 8,
                        }}>
                        LIVE FROM THE COMMUNITY
                     </div>
                     <div
                        style={{
                           fontSize: 28,
                           fontWeight: 900,
                           color: T.dark,
                           letterSpacing: "-0.02em",
                        }}>
                        Recent Investigations
                     </div>
                  </div>
                  <button
                     style={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: T.indigo,
                        background: "#eff6ff",
                        border: "1.5px solid #c7d2fe",
                        borderRadius: 8,
                        padding: "8px 16px",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                     }}>
                     View All{" "}
                     <ArrowRight
                        size={13}
                        color={T.indigo}
                     />
                  </button>
               </div>
               <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 20 }}>
                  {recentPosts.map((p, i) => (
                     <div
                        key={i}
                        style={{
                           border: "1.5px solid #e5e7eb",
                           borderRadius: 12,
                           overflow: "hidden",
                           cursor: "pointer",
                        }}>
                        <div
                           style={{
                              height: 120,
                              background: "linear-gradient(135deg,#e0e7ff,#f3f4f6)",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              position: "relative",
                              borderBottom: `3px solid ${bc(p.verdict)}`,
                           }}>
                           <Image
                              size={28}
                              color={T.gray}
                              strokeWidth={1.5}
                           />
                           <div style={{ position: "absolute", top: 10, right: 10 }}>
                              <VerdictBadge verdict={p.verdict} />
                           </div>
                        </div>
                        <div style={{ padding: "14px 16px" }}>
                           <div
                              style={{
                                 fontSize: 14,
                                 fontWeight: 800,
                                 color: "#111827",
                                 marginBottom: 6,
                              }}>
                              {p.title}
                           </div>
                           <div style={{ fontSize: 11, color: T.gray, lineHeight: 1.6 }}>
                              {p.sub}
                           </div>
                           <div
                              style={{
                                 marginTop: 10,
                                 fontSize: 10,
                                 color: T.gray,
                                 display: "flex",
                                 alignItems: "center",
                                 gap: 4,
                              }}>
                              <Activity
                                 size={10}
                                 color={T.gray}
                              />{" "}
                              AI Confidence: <strong>{p.confidence}%</strong>
                           </div>
                        </div>
                     </div>
                  ))}
               </div>
            </div>
         </div>
         {/* Trust Score CTA */}
         <div
            style={{
               background: `linear-gradient(135deg,${T.dark},#2d2a6e)`,
               padding: "72px 48px",
            }}>
            <div style={{ maxWidth: 700, margin: "0 auto", textAlign: "center" }}>
               <TrustGauge score={82} />
               <div
                  style={{
                     fontSize: 32,
                     fontWeight: 900,
                     color: "#fff",
                     letterSpacing: "-0.02em",
                     marginTop: 16,
                     marginBottom: 12,
                  }}>
                  Build Your Trust Score
               </div>
               <div
                  style={{
                     fontSize: 14,
                     color: "rgba(255,255,255,0.65)",
                     lineHeight: 1.7,
                     marginBottom: 28,
                     maxWidth: 480,
                     margin: "0 auto 28px",
                  }}>
                  Every piece of evidence you submit, every vote you cast — it all builds your
                  credibility score. Trusted contributors have more weight in community decisions.
               </div>
               <button
                  style={{
                     fontSize: 14,
                     fontWeight: 800,
                     color: T.indigo,
                     background: "#fff",
                     border: "none",
                     borderRadius: 10,
                     padding: "14px 32px",
                     cursor: "pointer",
                  }}>
                  Join the Community →
               </button>
            </div>
         </div>
         {/* Footer */}
         <div
            style={{
               background: T.dark,
               padding: "32px 48px",
               display: "flex",
               justifyContent: "space-between",
               alignItems: "center",
            }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
               <Logo size={14} />
               <span style={{ color: "rgba(255,255,255,0.6)", fontSize: 12 }}>
                  © 2025 TruthLens. Fighting misinformation together.
               </span>
            </div>
            <div style={{ display: "flex", gap: 20 }}>
               {["Privacy", "Terms", "Contact", "API"].map((l) => (
                  <span
                     key={l}
                     style={{
                        fontSize: 11,
                        color: "rgba(255,255,255,0.4)",
                        cursor: "pointer",
                        fontWeight: 600,
                     }}>
                     {l}
                  </span>
               ))}
            </div>
         </div>
      </div>
   );
};

// ─── Root App ─────────────────────────────────────────────────────────────────
const VIEWS = [
   { id: "design", Icon: Palette, label: "Design System" },
   { id: "ext-popup", Icon: ScanLine, label: "Ext. Popup" },
   { id: "ext-cards", Icon: Layers, label: "Injection Cards" },
   { id: "ext-minimized", Icon: Minimize2, label: "Ext. States" },
   { id: "auth", Icon: Shield, label: "Auth Pages" },
   { id: "onboarding", Icon: Rocket, label: "Onboarding" },
   { id: "dashboard", Icon: LayoutDashboard, label: "Dashboard" },
   { id: "feed", Icon: Globe, label: "Community Feed" },
   { id: "thread", Icon: MessageCircle, label: "Thread Detail" },
   { id: "create-thread", Icon: PlusCircle, label: "Create Thread" },
   { id: "user-profile", Icon: UserCircle, label: "User Profile" },
   { id: "notifications", Icon: Bell, label: "Notifications" },
   { id: "settings", Icon: Settings, label: "Settings" },
   { id: "trust-breakdown", Icon: PieChart, label: "Trust Score" },
   { id: "empty-states", Icon: HelpCircle, label: "Empty States" },
   { id: "moderation", Icon: AlertOctagon, label: "Moderation" },
   { id: "mobile-feed", Icon: Smartphone, label: "Mobile Feed" },
   { id: "landing", Icon: Rocket, label: "Landing Page" },
];
const DESC = {
   design:
      "Token reference, verdict states, icon map, and typography scale for the entire TruthLens platform.",
   "ext-popup": "380×520px popup with 3 tabbed input modes: Snip, Upload, and Scan URL.",
   "ext-cards":
      "React portals injected into host pages — Loading state and Analysis Result states.",
   "ext-minimized":
      "Minimized pill, dismissed toast, and passive scanning indicator states on host webpages.",
   auth: "Split-screen booklet layout — branded left panel with stats or features, clean form on the right.",
   onboarding:
      "4-step post-registration wizard: Welcome → Install Extension → First Scan → Complete.",
   dashboard:
      "User's personal space: Profile + Trust Score gauge, scan history, and contributions.",
   feed: "Facebook-style post feed with snipped images, verdict overlays, and reaction/action rows.",
   thread:
      "Full post view with collapsible evidence form and tabbed Comments / Evidence Board section.",
   "create-thread":
      "Thread creation form opened from the extension 'Ask the Community?' button — pre-populated with snipped content, 2-step flow.",
   "user-profile":
      "Public profile page for other users — Trust Score, contribution history, follow action.",
   notifications:
      "Tabbed notification feed (All / Votes / Evidence / System) with read/unread states.",
   settings:
      "Account, notification preferences, extension settings, privacy controls, and danger zone.",
   "trust-breakdown":
      "Modal showing weighted Trust Score formula — accuracy, votes, volume, tenure.",
   "empty-states":
      "Empty state cards for all data-empty views, plus PostCard and Evidence skeleton loaders.",
   moderation:
      "Admin panel with flag queue, verdict override controls, and moderation stat headers.",
   "mobile-feed":
      "390px iPhone frame showing the mobile-adapted feed layout with bottom tab navigation.",
   landing:
      "Redesigned public landing page — hero, stats, how it works, recent investigations, Trust Score CTA.",
};
const TITLE = {
   design: "Design System Reference",
   "ext-popup": "The Browser Extension Popup",
   "ext-cards": "Content Script Injection Cards",
   "ext-minimized": "Extension Minimized & Dismissed States",
   auth: "Authentication Pages",
   onboarding: "Post-Registration Onboarding Flow",
   dashboard: "Personal Dashboard",
   feed: "Community Feed",
   thread: "Thread Detail Page",
   "create-thread": "Create Thread (from Extension)",
   "user-profile": "Public User Profile",
   notifications: "Notifications Page",
   settings: "Settings Page",
   "trust-breakdown": "Trust Score Breakdown Modal",
   "empty-states": "Empty States & Skeleton Loaders",
   moderation: "Moderation / Admin Panel",
   "mobile-feed": "Mobile Feed (390px)",
   landing: "Landing Page (Redesigned)",
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
         {/* Page header — only for constrained views */}
         {active !== "auth" &&
            active !== "feed" &&
            active !== "thread" &&
            active !== "dashboard" &&
            active !== "user-profile" &&
            active !== "notifications" &&
            active !== "settings" &&
            active !== "moderation" &&
            active !== "onboarding" &&
            active !== "landing" && (
               <div style={{ padding: "32px 32px 0", maxWidth: 1200, margin: "0 auto" }}>
                  <div style={{ marginBottom: 28 }}>
                     <div
                        style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
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
               </div>
            )}

         {/* Auth — full bleed, no maxWidth, no side padding */}
         {active === "auth" && (
            <div style={{ padding: "0 0 48px" }}>
               <AuthPages />
            </div>
         )}

         {/* Design, Ext-Popup, Ext-Cards, Ext-Minimized, Trust Breakdown, Empty States, Mobile Feed — constrained to 1200px */}
         {(active === "design" ||
            active === "ext-popup" ||
            active === "ext-cards" ||
            active === "ext-minimized" ||
            active === "trust-breakdown" ||
            active === "empty-states" ||
            active === "mobile-feed") && (
            <div style={{ padding: "0 32px 48px", maxWidth: 1200, margin: "0 auto" }}>
               {active === "design" && <DesignSystem />}
               {active === "ext-popup" && <ExtensionPopup />}
               {active === "ext-cards" && <ContentCards />}
               {active === "ext-minimized" && <ExtMinimizedStates />}
               {active === "trust-breakdown" && <TrustBreakdown />}
               {active === "empty-states" && <EmptyStates />}
               {active === "mobile-feed" && <MobileFeed />}
            </div>
         )}

         {/* Feed, Thread, Dashboard, User Profile, Notifications, Settings, Moderation — full bleed in BrowserChrome */}
         {(active === "feed" ||
            active === "thread" ||
            active === "create-thread" ||
            active === "dashboard" ||
            active === "user-profile" ||
            active === "notifications" ||
            active === "settings" ||
            active === "moderation") && (
            <div style={{ padding: "0 0 48px" }}>
               <BrowserChrome
                  url={
                     active === "feed"
                        ? "community"
                        : active === "thread"
                          ? "thread/1042"
                          : active === "create-thread"
                            ? "thread/new"
                            : active === "dashboard"
                              ? "dashboard"
                              : active === "user-profile"
                                ? "u/factchecker_ph"
                                : active === "notifications"
                                  ? "notifications"
                                  : active === "settings"
                                    ? "settings"
                                    : "moderation/queue"
                  }>
                  {active === "feed" && <CommunityFeed />}
                  {active === "thread" && <ThreadDetail />}
                  {active === "create-thread" && <CreateThread />}
                  {active === "dashboard" && <PersonalDashboard />}
                  {active === "user-profile" && <UserProfilePage />}
                  {active === "notifications" && <NotificationsPage />}
                  {active === "settings" && <SettingsPage />}
                  {active === "moderation" && <ModerationPanel />}
               </BrowserChrome>
               {/* Annotations below the frame */}
               {active === "feed" && (
                  <div
                     style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: 16,
                        marginTop: 28,
                        padding: "0 32px",
                     }}>
                     <Ann
                        title="Visual Structure"
                        BoxIcon={Ruler}
                        color={T.indigo}
                        items={[
                           "Full page: bg-gray-100 · AppNav (sticky) → FilterBar → CreatePrompt → PostCards",
                           "PostCard: Header → Caption → SnippedImage → VerdictOverlay → Reactions → Actions",
                           "Feed column: max-w-[680px] mx-auto — centered, same as Facebook/Twitter feed",
                           "Verdict overlay: absolute bottom of image, border-t-4 semantic verdict color",
                        ]}
                     />
                     <Ann
                        title="React Components"
                        BoxIcon={Braces}
                        color="#7c3aed"
                        items={[
                           "<CommunityFeed> — filter state, paginated post list",
                           "<AppNav> — sticky top nav with active page highlight",
                           "<FilterBar> — activeFilter pill state, onFilterChange prop",
                           "<CreatePostPrompt> — opens snip flow or upload modal",
                           "<PostCard> — full post unit, receives post object",
                           "<SnippedImageBlock> — ImgPlaceholder + VerdictOverlay strip",
                           "<ReactionBar> — icon stack + counts",
                           "<PostActionRow> — React / Comment / Add Evidence",
                        ]}
                     />
                     <Ann
                        title="Tailwind / UX Advice"
                        BoxIcon={Palette}
                        color={T.green}
                        items={[
                           "PostCard: rounded-2xl shadow-sm hover:shadow-md transition-shadow",
                           "Image block: aspect-video or min-h-[200px] bg-gray-100",
                           "VerdictOverlay: absolute bottom-0 inset-x-0 bg-[verdict]/10 border-t-4",
                           "'Add Evidence': text-indigo-600 font-bold — distinct from other action btns",
                           "Infinite scroll: IntersectionObserver on last card sentinel",
                           "Filter pills: active = bg-indigo-600 text-white, inactive = bg-gray-100 text-gray-500",
                        ]}
                     />
                     <Ann
                        title="UX Patterns"
                        BoxIcon={Puzzle}
                        color={T.amber}
                        items={[
                           "Click image → navigates to Thread Detail page",
                           "Click 'Comment' → expands inline input below ActionRow",
                           "Click 'Add Evidence' → Thread Detail, auto-opens Evidence form",
                           "MoreHorizontal menu → Report / Share / Copy Link",
                           "Verdict overlay: informational only, non-interactive in feed view",
                        ]}
                     />
                  </div>
               )}
               {active === "thread" && (
                  <div
                     style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: 16,
                        marginTop: 28,
                        padding: "0 32px",
                     }}>
                     <Ann
                        title="Visual Structure"
                        BoxIcon={Ruler}
                        color={T.indigo}
                        items={[
                           "Full page: AppNav (sticky) → Breadcrumb bar → PostCard → EvidenceToggleBtn → TabbedSection",
                           "Breadcrumb: Community Feed → Thread #1042 · VerdictBadge right-aligned",
                           "Content column: max-w-[680px] mx-auto — matches feed column width",
                           "EvidenceToggleBtn merges with form below via shared border (borderTop: none)",
                        ]}
                     />
                     <Ann
                        title="React Components"
                        BoxIcon={Braces}
                        color="#7c3aed"
                        items={[
                           "<ThreadDetail> — fetches thread by :id, owns showForm + activeTab state",
                           "<AppNav> — same component as Community Feed, activePage='feed'",
                           "<BreadcrumbBar> — static back-link + current thread title + VerdictBadge",
                           "<PostCard> — reused from Community Feed, no changes needed",
                           "<EvidenceToggleButton> — toggles showEvidenceForm boolean",
                           "<EvidenceFormPanel> — conditionally rendered, controlled inputs",
                           "<TabbedSection> — Comments | Evidence Board tab bar + active panel",
                           "<EvidenceCard> — trust tier border-l-4, source link, VoteButtons",
                        ]}
                     />
                     <Ann
                        title="UX / Tailwind Advice"
                        BoxIcon={Palette}
                        color={T.green}
                        items={[
                           "Toggle btn: bg/border/text flips when open — clear visual state signal",
                           "Collapsible form: border-t-none merges with toggle button above it",
                           "Tab bar: border-b-2 border-indigo-600 on active — same pattern as Extension Popup",
                           "Comment bubble: bg-gray-50 rounded-tr-xl rounded-b-xl (Facebook-style)",
                           "Evidence border-l-4 tier: green ≥75 · amber 45–74 · red <45 (submitter Trust Score)",
                        ]}
                     />
                     <Ann
                        title="Interaction Flow"
                        BoxIcon={Hash}
                        color={T.red}
                        items={[
                           "Feed 'Add Evidence' → Thread Detail, auto-sets showForm=true",
                           "Feed 'Comment' → Thread Detail, activeTab='comments'",
                           "Submitting evidence form → optimistic insert to Evidence Board, switch to evidence tab",
                           "Tab switch is instant — data already in component state, no loading",
                           "Evidence sorted: weighted_score DESC on initial load",
                        ]}
                     />
                  </div>
               )}
               {active === "create-thread" && (
                  <div
                     style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: 16,
                        marginTop: 28,
                        padding: "0 32px",
                     }}>
                     <Ann
                        title="Visual Structure"
                        BoxIcon={Ruler}
                        color={T.indigo}
                        items={[
                           "Full page: white bg · AppNav → context banner → 2-col layout (form + sidebar)",
                           "Sub-header: same 3px verdict-color border-bottom pattern as Thread Detail",
                           "Step indicator in sub-header: 2 steps — Review Claim · Confirm & Post",
                           "Step 1: left col = form fields · right col = sticky sidebar (AI analysis, duplicates, guidelines)",
                           "Step 2: full-width PostCard preview + Edit / Post to Community buttons",
                           "Context banner below sub-header: shows source domain + snip timestamp",
                        ]}
                     />
                     <Ann
                        title="React Components"
                        BoxIcon={Braces}
                        color="#7c3aed"
                        items={[
                           "<CreateThread> — owns step (1|2) + category state",
                           "<AppNav> — activePage='feed' (user is still in the feed context)",
                           "<SnipPreviewCard> — shows the captured image + source URL + Re-snip button",
                           "<CategoryPicker> — 4-option grid (Misleading / Fake / Unverified / Satire)",
                           "<AiAnalysisSidebar> — verdict badge + confidence bar + low-confidence note",
                           "<DuplicateCheck> — lists similar existing threads with View links",
                           "<PostCard> — reused in step 2 preview, read-only (no onClick)",
                           "Route: /thread/new?snap={encodedUrl}&claim={encodedText}",
                        ]}
                     />
                     <Ann
                        title="Extension → Web Handoff"
                        BoxIcon={Layers}
                        color={T.amber}
                        items={[
                           "Extension passes data via URL query params or localStorage snapshot",
                           "Params: snap (source URL), claim (extracted text), confidence, verdict",
                           "Page reads params on mount → pre-populates all fields",
                           "If user is not logged in → redirect to /login?next=/thread/new&{params}",
                           "Re-snip button: re-opens extension snip tool on the same source URL",
                           "Save Draft: persists form state to localStorage for later completion",
                        ]}
                     />
                     <Ann
                        title="UX Decisions"
                        BoxIcon={Puzzle}
                        color={T.green}
                        items={[
                           "2-step flow: separates data entry from social commitment (posting)",
                           "Step 2 preview: user sees exactly how the thread will look before posting",
                           "Duplicate check sidebar: reduces noise in the feed proactively",
                           "Category picker: overrides AI suggestion — community context > AI",
                           "AI analysis is informational only — never blocks the user from posting",
                           "Trust Score earned when flagged claim gets verified by the community",
                        ]}
                     />
                  </div>
               )}
               {active === "dashboard" && (
                  <div
                     style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: 16,
                        marginTop: 28,
                        padding: "0 32px",
                     }}>
                     <Ann
                        title="Visual Structure"
                        BoxIcon={Ruler}
                        color={T.indigo}
                        items={[
                           "Full page: AppNav (sticky, activePage='dashboard') → content column max-w-[900px] mx-auto",
                           "ProfileHeader: Avatar · username · bio · TrustGauge · Scans/Votes stats",
                           "My Scans: white card with table — thumbnail icon, claim text, VerdictBadge, date, actions",
                           "My Contributions: 2-col grid of contribution cards with type badge + VerdictBadge",
                        ]}
                     />
                     <Ann
                        title="React Components"
                        BoxIcon={Braces}
                        color="#7c3aed"
                        items={[
                           "<PersonalDashboard> — top-level page, owns no interactive state",
                           "<AppNav activePage='dashboard'> — 'Dashboard' tab underlined in indigo",
                           "<ProfileHeader> — Avatar, username, bio, TrustGauge, stat pills",
                           "<TrustGauge> — SVG ring gauge, color = green ≥80 / amber ≥50 / red <50",
                           "<ScansTable> — table with VerdictBadge per row, View + Share actions",
                           "<ContributionCard> — type label (Thread/Evidence), title, verdict, upvote count",
                        ]}
                     />
                     <Ann
                        title="Tailwind / UX Advice"
                        BoxIcon={Palette}
                        color={T.green}
                        items={[
                           "AppNav 'Dashboard' tab: border-b-2 border-indigo-600 text-white (active state)",
                           "ProfileHeader: bg-white rounded-xl shadow-sm p-6 flex items-center gap-6",
                           "TrustGauge: right-aligned in profile header — draws eye to credibility signal",
                           "Table rows: hover:bg-gray-50 cursor-pointer transition-colors",
                           "Contribution cards: border-l-4 using verdict semantic color for instant scanning",
                        ]}
                     />
                     <Ann
                        title="Architecture Note"
                        BoxIcon={Hash}
                        color={T.amber}
                        items={[
                           "Sidebar removed — AppNav replaces it for consistency with Feed and Thread Detail",
                           "Page width is 900px (vs 680px for feed) — dashboard is data-dense, not a reading feed",
                           "Navigation state: AppNav activePage prop is the only change between pages",
                           "TrustGauge and VerdictBadge are shared components — define once in components/ui/",
                        ]}
                     />
                  </div>
               )}
            </div>
         )}

         {/* Onboarding — full bleed (own browser frame built-in) */}
         {active === "onboarding" && <OnboardingFlow />}

         {/* Landing Page — full bleed */}
         {active === "landing" && (
            <div style={{ padding: "0 0 48px" }}>
               <LandingPage />
               <div
                  style={{
                     display: "grid",
                     gridTemplateColumns: "1fr 1fr",
                     gap: 16,
                     marginTop: 28,
                     padding: "0 32px",
                  }}>
                  <Ann
                     title="Visual Structure"
                     BoxIcon={Ruler}
                     color={T.indigo}
                     items={[
                        "Sticky Navbar (white + blur) → Hero (dark gradient) → How It Works → Recent Investigations → Trust Score CTA → Footer",
                        "Hero: 2-col grid — copy/CTAs left, floating extension mockup right",
                        "Stats row lives inside the hero — not buried below the fold",
                        "Floating Result Card overlaid on fake feed mockup = product-in-context storytelling",
                     ]}
                  />
                  <Ann
                     title="Brand Fixes vs Current Page"
                     BoxIcon={Palette}
                     color={T.red}
                     items={[
                        "Teal/cyan → Trust Indigo (#4f46e5) — matches the app exactly",
                        "Hero gradient: dark navy → indigo (same as auth page and sidebar)",
                        "CTA button: solid indigo with UPPERCASE tracking (not teal)",
                        "Second CTA added: 'Watch Demo' for users not ready to install",
                     ]}
                  />
                  <Ann
                     title="Conversion Mechanics"
                     BoxIcon={Rocket}
                     color={T.green}
                     items={[
                        "Stats (12,040+ verified, 98% accuracy) moved into hero — visible before any scroll",
                        "'Recent Investigations' section = social proof feed preview — shows product value live",
                        "Trust Score CTA section converts community-curious users who won't install the extension",
                        "Footer links: Privacy, Terms, Contact, API — signals legitimacy to skeptical users",
                     ]}
                  />
                  <Ann
                     title="Components"
                     BoxIcon={Braces}
                     color={T.violet}
                     items={[
                        "<LandingNavbar> — sticky, backdrop-blur, Login + Get Started CTAs",
                        "<HeroSection> — grid layout, stats row, dual CTAs, floating ResultCard mockup",
                        "<HowItWorks> — 3-step grid with icon tiles",
                        "<RecentInvestigations> — static 3-card grid, links to community feed",
                        "<TrustScoreCTA> — dark panel matching brand, single join CTA",
                        "<LandingFooter> — logo, tagline, legal links",
                     ]}
                  />
               </div>
            </div>
         )}
      </div>
   );
}
